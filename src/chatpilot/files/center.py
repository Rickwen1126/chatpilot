"""FileHandleCenter implementation."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Mapping

from chatpilot.adapters.protocol import ChannelAdapter
from chatpilot.core.time_service import TimeService
from chatpilot.files.layout import (
    DEFAULT_FILE_ASSET_ROOT,
    build_asset_paths,
    ensure_asset_dirs,
)
from chatpilot.files.models import (
    CanonicalFileHandle,
    FetchStatus,
    MaterializedAsset,
    RetentionClass,
    SourceFetchResult,
    SourceHandleInput,
    StorageBackend,
)
from chatpilot.files.policy import compute_expires_at, default_scan_status
from chatpilot.files.store import (
    SqliteFileStore,
    build_asset_from_row,
    build_handle_from_row,
)

logger = logging.getLogger(__name__)


class FileHandleCenter:
    """Canonical file registry, download orchestrator, and local asset manager."""

    def __init__(
        self,
        store: SqliteFileStore,
        adapters: Mapping[str, ChannelAdapter],
        *,
        asset_root: str | Path | None = None,
    ) -> None:
        self._store = store
        self._adapters = adapters
        self._asset_root = Path(asset_root) if asset_root is not None else DEFAULT_FILE_ASSET_ROOT
        self._prefetch_tasks: dict[str, asyncio.Task[MaterializedAsset]] = {}

    async def register(
        self,
        source: SourceHandleInput,
        *,
        retention_class: RetentionClass | str = RetentionClass.default,
        is_pinned: bool = False,
    ) -> CanonicalFileHandle:
        now = TimeService.get().utc_now()
        file_id = str(uuid.uuid4())
        handle = CanonicalFileHandle.from_source(file_id=file_id, source=source)
        expires_at = compute_expires_at(retention_class, from_time=now)
        await self._store.create_file(
            handle,
            created_at=now,
            expires_at=expires_at,
            retention_class=retention_class,
            is_pinned=is_pinned,
        )
        logger.info(
            "[file] register file_id=%s route=%s kind=%s platform=%s",
            file_id,
            source.route_id,
            source.kind.value,
            source.platform,
        )
        return handle

    async def register_local_file(
        self,
        *,
        route_id: str,
        local_path: str | Path,
        kind: str,
        filename: str | None = None,
        mime_type: str | None = None,
        retention_class: RetentionClass | str = RetentionClass.default,
        is_pinned: bool = False,
        derived_from_file_id: str | None = None,
        generated_by_tool: str | None = None,
        generated_by_pipeline: str | None = None,
    ) -> CanonicalFileHandle:
        source_path = Path(local_path)
        if not source_path.exists():
            raise FileNotFoundError(source_path)

        return await self.register_bytes_file(
            route_id=route_id,
            data=source_path.read_bytes(),
            kind=kind,
            filename=filename or source_path.name,
            mime_type=mime_type,
            retention_class=retention_class,
            is_pinned=is_pinned,
            derived_from_file_id=derived_from_file_id,
            generated_by_tool=generated_by_tool,
            generated_by_pipeline=generated_by_pipeline,
            origin_type="local_import",
        )

    async def register_bytes_file(
        self,
        *,
        route_id: str,
        data: bytes,
        kind: str,
        filename: str | None = None,
        mime_type: str | None = None,
        retention_class: RetentionClass | str = RetentionClass.default,
        is_pinned: bool = False,
        derived_from_file_id: str | None = None,
        generated_by_tool: str | None = None,
        generated_by_pipeline: str | None = None,
        origin_type: str = "generated",
    ) -> CanonicalFileHandle:
        if not data:
            raise ValueError("generated file data must not be empty")

        handle = await self.register(
            SourceHandleInput(
                route_id=route_id,
                platform="internal",
                kind=kind,
                native_locator=f"{origin_type}:{uuid.uuid4()}",
                filename=filename,
                mime_type=mime_type,
                platform_context={"origin_type": origin_type},
            ),
            retention_class=retention_class,
            is_pinned=is_pinned,
        )

        now = TimeService.get().utc_now()
        asset = self._persist_local_asset(
            handle,
            SourceFetchResult(
                data=data,
                filename=filename,
                mime_type=mime_type,
            ),
            now=now,
            expires_at=(await self._require_file(handle.file_id)).get("expires_at"),
        )
        await self._store.update_file(
            handle.file_id,
            fetch_status=FetchStatus.ready,
            storage_backend=StorageBackend.local,
            local_path=asset.local_path,
            sha256=asset.sha256,
            size_bytes=asset.size_bytes,
            materialized_at=asset.materialized_at,
            last_accessed_at=asset.materialized_at,
            source_filename=asset.filename,
            source_mime_type=asset.mime_type,
        )

        await self._link_generated_file(
            handle.file_id,
            derived_from_file_id=derived_from_file_id,
            generated_by_tool=generated_by_tool,
            generated_by_pipeline=generated_by_pipeline,
        )

        logger.info(
            "[file] register internal file_id=%s route=%s origin=%s",
            handle.file_id,
            route_id,
            origin_type,
        )
        return handle

    async def download_now(self, file_id: str) -> MaterializedAsset:
        row = await self._require_file(file_id)
        asset = build_asset_from_row(row)
        if asset is not None and asset.local_path and Path(asset.local_path).exists():
            now = TimeService.get().utc_now()
            await self._store.update_file(file_id, last_accessed_at=now)
            return asset

        handle = build_handle_from_row(row)
        adapter = self._adapters.get(handle.platform)
        if adapter is None:
            raise RuntimeError(
                f"No adapter registered for platform '{handle.platform}'"
            )

        await self._store.update_file(file_id, fetch_status=FetchStatus.fetching)
        try:
            result = await adapter.fetch_source_file(
                SourceHandleInput(
                    route_id=handle.route_id,
                    platform=handle.platform,
                    kind=handle.kind,
                    native_locator=handle.native_locator,
                    filename=handle.filename,
                    mime_type=handle.mime_type,
                    platform_context=handle.platform_context,
                )
            )
            if result is None:
                raise RuntimeError(
                    f"Adapter '{handle.platform}' returned no file data for {file_id}"
                )

            now = TimeService.get().utc_now()
            asset = self._persist_local_asset(
                handle,
                result,
                now=now,
                expires_at=row.get("expires_at"),
            )
            await self._store.update_file(
                file_id,
                fetch_status=FetchStatus.ready,
                storage_backend=StorageBackend.local,
                local_path=asset.local_path,
                sha256=asset.sha256,
                size_bytes=asset.size_bytes,
                materialized_at=asset.materialized_at,
                last_accessed_at=asset.materialized_at,
                source_filename=asset.filename,
                source_mime_type=asset.mime_type,
            )
            logger.info(
                "[file] download file_id=%s backend=%s bytes=%s",
                file_id,
                asset.storage_backend.value,
                asset.size_bytes,
            )
            return asset
        except Exception:
            await self._store.update_file(file_id, fetch_status=FetchStatus.failed)
            raise

    async def prefetch(self, file_id: str) -> str:
        task_id = str(uuid.uuid4())
        task = asyncio.create_task(self.download_now(file_id))
        self._prefetch_tasks[task_id] = task

        def _cleanup(_task: asyncio.Task[MaterializedAsset]) -> None:
            try:
                _task.result()
            except Exception:
                logger.exception(
                    "[file] prefetch failed file_id=%s task=%s",
                    file_id,
                    task_id,
                )
            self._prefetch_tasks.pop(task_id, None)

        task.add_done_callback(_cleanup)
        logger.info("[file] prefetch scheduled file_id=%s task=%s", file_id, task_id)
        return task_id

    async def get_asset(self, file_id: str) -> MaterializedAsset | None:
        row = await self._store.get_file(file_id)
        if row is None:
            return None
        return build_asset_from_row(row)

    async def get_handle(self, file_id: str) -> CanonicalFileHandle | None:
        row = await self._store.get_file(file_id)
        if row is None:
            return None
        return build_handle_from_row(row)

    async def find_source_handle(
        self,
        *,
        route_id: str,
        platform: str,
        native_locator: str,
    ) -> CanonicalFileHandle | None:
        row = await self._store.find_file_by_source(
            route_id=route_id,
            platform=platform,
            native_locator=native_locator,
        )
        if row is None:
            return None
        return build_handle_from_row(row)

    async def list_route_files(self, route_id: str) -> list[dict]:
        return await self._store.list_files_for_route(route_id)

    async def add_note(
        self,
        file_id: str,
        *,
        note_type: str,
        content: str,
        metadata: dict | None = None,
        created_by: str | None = None,
    ) -> str:
        return await self._store.add_note(
            file_id=file_id,
            note_type=note_type,
            content=content,
            metadata=metadata,
            created_by=created_by,
        )

    async def list_notes(
        self,
        file_id: str,
        *,
        note_type: str | None = None,
    ) -> list[dict]:
        return await self._store.list_notes(file_id, note_type=note_type)

    async def add_relation(
        self,
        *,
        from_file_id: str,
        relation_type: str,
        to_file_id: str | None = None,
        subject_type: str | None = None,
        subject_id: str | None = None,
        metadata: dict | None = None,
    ) -> str:
        return await self._store.add_relation(
            from_file_id=from_file_id,
            relation_type=relation_type,
            to_file_id=to_file_id,
            subject_type=subject_type,
            subject_id=subject_id,
            metadata=metadata,
        )

    async def list_relations(
        self,
        *,
        from_file_id: str | None = None,
        subject_type: str | None = None,
        subject_id: str | None = None,
    ) -> list[dict]:
        return await self._store.list_relations(
            from_file_id=from_file_id,
            subject_type=subject_type,
            subject_id=subject_id,
        )

    async def ensure_local(self, file_id: str) -> str:
        asset = await self.get_asset(file_id)
        if asset is None or not asset.local_path or not Path(asset.local_path).exists():
            asset = await self.download_now(file_id)
        if not asset.local_path:
            raise RuntimeError(f"File '{file_id}' has no local path")
        return asset.local_path

    async def cleanup_expired(
        self,
        *,
        before: datetime | None = None,
    ) -> int:
        deadline = before or TimeService.get().utc_now()
        expired_rows = await self._store.list_expired_files(before=deadline)
        cleaned = 0
        for row in expired_rows:
            local_path = row.get("local_path")
            if local_path:
                try:
                    file_dir = Path(local_path).parent
                    if file_dir.exists():
                        shutil.rmtree(file_dir)
                except FileNotFoundError:
                    pass
            await self._store.update_file(
                row["file_id"],
                fetch_status=FetchStatus.expired,
                storage_backend=StorageBackend.none,
                local_path=None,
                public_url=None,
            )
            cleaned += 1
        if cleaned:
            logger.info("[file] cleanup expired count=%d", cleaned)
        return cleaned

    async def _link_generated_file(
        self,
        file_id: str,
        *,
        derived_from_file_id: str | None = None,
        generated_by_tool: str | None = None,
        generated_by_pipeline: str | None = None,
    ) -> None:
        if derived_from_file_id:
            await self.add_relation(
                from_file_id=file_id,
                relation_type="derived_from",
                to_file_id=derived_from_file_id,
            )
        if generated_by_tool:
            await self.add_relation(
                from_file_id=file_id,
                relation_type="generated_by_tool",
                subject_type="tool",
                subject_id=generated_by_tool,
            )
        if generated_by_pipeline:
            await self.add_relation(
                from_file_id=file_id,
                relation_type="generated_by_pipeline",
                subject_type="pipeline",
                subject_id=generated_by_pipeline,
            )

    def _persist_local_asset(
        self,
        handle: CanonicalFileHandle,
        result: SourceFetchResult,
        *,
        now: datetime,
        expires_at: str | None,
    ) -> MaterializedAsset:
        paths = build_asset_paths(
            handle.route_id,
            handle.file_id,
            root=self._asset_root,
        )
        ensure_asset_dirs(paths)
        paths.source_path.write_bytes(result.data)
        sha256 = hashlib.sha256(result.data).hexdigest()
        filename = result.filename or handle.filename
        mime_type = result.mime_type or handle.mime_type
        asset = MaterializedAsset(
            file_id=handle.file_id,
            storage_backend=StorageBackend.local,
            local_path=str(paths.source_path),
            sha256=sha256,
            size_bytes=result.normalized_size_bytes(),
            scan_status=default_scan_status(),
            materialized_at=now,
            expires_at=datetime.fromisoformat(expires_at) if expires_at else None,
            filename=filename,
            mime_type=mime_type,
        )
        paths.meta_path.write_text(
            json.dumps(
                {
                    "file_id": handle.file_id,
                    "route_id": handle.route_id,
                    "platform": handle.platform,
                    "native_locator": handle.native_locator,
                    "kind": handle.kind.value,
                    "filename": filename,
                    "mime_type": mime_type,
                    "sha256": sha256,
                    "size_bytes": asset.size_bytes,
                    "materialized_at": now.isoformat(),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return asset

    async def _require_file(self, file_id: str) -> dict:
        row = await self._store.get_file(file_id)
        if row is None:
            raise RuntimeError(f"Unknown file_id: {file_id}")
        return row
