"""SQLite-backed file asset store."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

import aiosqlite

from chatpilot.core.time_service import TimeService
from chatpilot.files.models import (
    CanonicalFileHandle,
    FetchStatus,
    MaterializedAsset,
    RetentionClass,
    ScanStatus,
    SourceHandleInput,
    StorageBackend,
)

logger = logging.getLogger(__name__)

CREATE_TABLES = """
CREATE TABLE IF NOT EXISTS file_assets (
    file_id TEXT PRIMARY KEY,
    route_id TEXT NOT NULL,
    source_platform TEXT NOT NULL,
    source_native_locator TEXT NOT NULL,
    source_kind TEXT NOT NULL,
    source_filename TEXT,
    source_mime_type TEXT,
    source_platform_context_json TEXT NOT NULL DEFAULT '{}',
    fetch_status TEXT NOT NULL DEFAULT 'registered',
    storage_backend TEXT NOT NULL DEFAULT 'none',
    local_path TEXT,
    public_url TEXT,
    sha256 TEXT,
    size_bytes INTEGER,
    scan_status TEXT NOT NULL DEFAULT 'unscanned',
    created_at TEXT NOT NULL,
    materialized_at TEXT,
    last_accessed_at TEXT,
    expires_at TEXT,
    is_pinned INTEGER NOT NULL DEFAULT 0,
    retention_class TEXT NOT NULL DEFAULT 'default'
);

CREATE TABLE IF NOT EXISTS file_relations (
    relation_id TEXT PRIMARY KEY,
    from_file_id TEXT NOT NULL,
    relation_type TEXT NOT NULL,
    to_file_id TEXT,
    subject_type TEXT,
    subject_id TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS file_notes (
    note_id TEXT PRIMARY KEY,
    file_id TEXT NOT NULL,
    note_type TEXT NOT NULL,
    content TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    created_by TEXT
);
"""

CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_file_assets_route_id ON file_assets(route_id);",
    (
        "CREATE INDEX IF NOT EXISTS idx_file_assets_source_lookup "
        "ON file_assets(source_platform, source_native_locator);"
    ),
    "CREATE INDEX IF NOT EXISTS idx_file_assets_fetch_status ON file_assets(fetch_status);",
    "CREATE INDEX IF NOT EXISTS idx_file_assets_expires_at ON file_assets(expires_at);",
    "CREATE INDEX IF NOT EXISTS idx_file_relations_from ON file_relations(from_file_id);",
    (
        "CREATE INDEX IF NOT EXISTS idx_file_relations_subject "
        "ON file_relations(subject_type, subject_id);"
    ),
    "CREATE INDEX IF NOT EXISTS idx_file_relations_type ON file_relations(relation_type);",
    "CREATE INDEX IF NOT EXISTS idx_file_notes_file_id ON file_notes(file_id);",
    "CREATE INDEX IF NOT EXISTS idx_file_notes_type ON file_notes(note_type);",
]


class SqliteFileStore:
    """SQLite WAL-mode persistence for canonical file assets."""

    def __init__(self, db_path: str = "data/files.db") -> None:
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def initialize(self) -> None:
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self._db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.executescript(CREATE_TABLES)
        for index in CREATE_INDEXES:
            await self._db.execute(index)
        await self._db.commit()
        logger.info("FileStore initialized at %s", self._db_path)

    async def close(self) -> None:
        if self._db is not None:
            await self._db.close()

    async def create_file(
        self,
        handle: CanonicalFileHandle,
        *,
        created_at: datetime,
        expires_at: datetime | None,
        retention_class: RetentionClass | str = RetentionClass.default,
        is_pinned: bool = False,
    ) -> None:
        db = self._require_db()
        await db.execute(
            """
            INSERT INTO file_assets (
                file_id, route_id, source_platform, source_native_locator,
                source_kind, source_filename, source_mime_type,
                source_platform_context_json, fetch_status, storage_backend,
                scan_status, created_at, expires_at, is_pinned,
                retention_class
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                handle.file_id,
                handle.route_id,
                handle.platform,
                handle.native_locator,
                handle.kind.value,
                handle.filename,
                handle.mime_type,
                json.dumps(handle.platform_context, ensure_ascii=False),
                FetchStatus.registered.value,
                StorageBackend.none.value,
                ScanStatus.unscanned.value,
                created_at.isoformat(),
                expires_at.isoformat() if expires_at else None,
                1 if is_pinned else 0,
                RetentionClass(retention_class).value,
            ),
        )
        await db.commit()

    async def get_file(self, file_id: str) -> dict[str, Any] | None:
        db = self._require_db()
        async with db.execute(
            "SELECT * FROM file_assets WHERE file_id = ?",
            (file_id,),
        ) as cursor:
            row = await cursor.fetchone()
        return _row_to_dict(row) if row is not None else None

    async def find_file_by_source(
        self,
        *,
        route_id: str,
        platform: str,
        native_locator: str,
    ) -> dict[str, Any] | None:
        db = self._require_db()
        async with db.execute(
            """
            SELECT * FROM file_assets
            WHERE route_id = ?
              AND source_platform = ?
              AND source_native_locator = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (route_id, platform, native_locator),
        ) as cursor:
            row = await cursor.fetchone()
        return _row_to_dict(row) if row is not None else None

    async def list_files_for_route(self, route_id: str) -> list[dict[str, Any]]:
        db = self._require_db()
        async with db.execute(
            "SELECT * FROM file_assets WHERE route_id = ? ORDER BY created_at DESC",
            (route_id,),
        ) as cursor:
            rows = await cursor.fetchall()
        return [_row_to_dict(row) for row in rows]

    async def update_file(self, file_id: str, **fields: Any) -> None:
        if not fields:
            return
        db = self._require_db()
        normalized = _normalize_update_fields(fields)
        sets = ", ".join(f"{key} = ?" for key in normalized)
        values = list(normalized.values()) + [file_id]
        await db.execute(
            f"UPDATE file_assets SET {sets} WHERE file_id = ?",
            values,
        )
        await db.commit()

    async def add_relation(
        self,
        *,
        from_file_id: str,
        relation_type: str,
        to_file_id: str | None = None,
        subject_type: str | None = None,
        subject_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        relation_id: str | None = None,
        created_at: datetime | None = None,
    ) -> str:
        db = self._require_db()
        relation_id = relation_id or str(uuid.uuid4())
        created_at = created_at or TimeService.get().utc_now()
        await db.execute(
            """
            INSERT INTO file_relations (
                relation_id, from_file_id, relation_type, to_file_id,
                subject_type, subject_id, metadata_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                relation_id,
                from_file_id,
                relation_type,
                to_file_id,
                subject_type,
                subject_id,
                json.dumps(metadata or {}, ensure_ascii=False),
                created_at.isoformat(),
            ),
        )
        await db.commit()
        return relation_id

    async def list_relations(
        self,
        *,
        from_file_id: str | None = None,
        subject_type: str | None = None,
        subject_id: str | None = None,
    ) -> list[dict[str, Any]]:
        db = self._require_db()
        clauses: list[str] = []
        params: list[Any] = []
        if from_file_id is not None:
            clauses.append("from_file_id = ?")
            params.append(from_file_id)
        if subject_type is not None:
            clauses.append("subject_type = ?")
            params.append(subject_type)
        if subject_id is not None:
            clauses.append("subject_id = ?")
            params.append(subject_id)
        where = " AND ".join(clauses) if clauses else "1=1"
        async with db.execute(
            f"SELECT * FROM file_relations WHERE {where} ORDER BY created_at ASC",
            params,
        ) as cursor:
            rows = await cursor.fetchall()
        return [_relation_row_to_dict(row) for row in rows]

    async def add_note(
        self,
        *,
        file_id: str,
        note_type: str,
        content: str,
        metadata: dict[str, Any] | None = None,
        created_by: str | None = None,
        note_id: str | None = None,
        created_at: datetime | None = None,
    ) -> str:
        db = self._require_db()
        note_id = note_id or str(uuid.uuid4())
        created_at = created_at or TimeService.get().utc_now()
        await db.execute(
            """
            INSERT INTO file_notes (
                note_id, file_id, note_type, content,
                metadata_json, created_at, created_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                note_id,
                file_id,
                note_type,
                content,
                json.dumps(metadata or {}, ensure_ascii=False),
                created_at.isoformat(),
                created_by,
            ),
        )
        await db.commit()
        return note_id

    async def list_notes(
        self,
        file_id: str,
        *,
        note_type: str | None = None,
    ) -> list[dict[str, Any]]:
        db = self._require_db()
        if note_type is None:
            query = (
                "SELECT * FROM file_notes WHERE file_id = ? "
                "ORDER BY created_at ASC"
            )
            params = (file_id,)
        else:
            query = (
                "SELECT * FROM file_notes WHERE file_id = ? AND note_type = ? "
                "ORDER BY created_at ASC"
            )
            params = (file_id, note_type)
        async with db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
        return [_note_row_to_dict(row) for row in rows]

    async def list_expired_files(
        self,
        *,
        before: datetime,
    ) -> list[dict[str, Any]]:
        db = self._require_db()
        async with db.execute(
            """
            SELECT * FROM file_assets
            WHERE expires_at IS NOT NULL
              AND expires_at <= ?
              AND is_pinned = 0
              AND fetch_status != ?
            ORDER BY expires_at ASC
            """,
            (before.isoformat(), FetchStatus.expired.value),
        ) as cursor:
            rows = await cursor.fetchall()
        return [_row_to_dict(row) for row in rows]

    def _require_db(self) -> aiosqlite.Connection:
        if self._db is None:
            raise RuntimeError("FileStore not initialized")
        return self._db


def build_handle_from_row(row: dict[str, Any]) -> CanonicalFileHandle:
    source = SourceHandleInput(
        route_id=row["route_id"],
        platform=row["source_platform"],
        kind=row["source_kind"],
        native_locator=row["source_native_locator"],
        filename=row.get("source_filename"),
        mime_type=row.get("source_mime_type"),
        platform_context=row.get("source_platform_context_json", {}),
    )
    return CanonicalFileHandle.from_source(
        file_id=row["file_id"],
        source=source,
    )


def build_asset_from_row(row: dict[str, Any]) -> MaterializedAsset | None:
    backend = StorageBackend(row["storage_backend"])
    if backend == StorageBackend.none:
        return None
    return MaterializedAsset(
        file_id=row["file_id"],
        storage_backend=backend,
        local_path=row.get("local_path"),
        public_url=row.get("public_url"),
        sha256=row.get("sha256"),
        size_bytes=row.get("size_bytes"),
        scan_status=ScanStatus(row["scan_status"]),
        materialized_at=_parse_optional_datetime(row.get("materialized_at")),
        expires_at=_parse_optional_datetime(row.get("expires_at")),
        filename=row.get("source_filename"),
        mime_type=row.get("source_mime_type"),
    )


def _normalize_update_fields(fields: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, value in fields.items():
        if isinstance(value, datetime):
            normalized[key] = value.isoformat()
        elif isinstance(value, Enum):  # type: ignore[name-defined]
            normalized[key] = value.value
        elif key.endswith("_json") and isinstance(value, dict):
            normalized[key] = json.dumps(value, ensure_ascii=False)
        else:
            normalized[key] = value
    return normalized


def _row_to_dict(row: aiosqlite.Row) -> dict[str, Any]:
    result = dict(row)
    result["source_platform_context_json"] = json.loads(
        result["source_platform_context_json"] or "{}"
    )
    result["is_pinned"] = bool(result["is_pinned"])
    return result


def _relation_row_to_dict(row: aiosqlite.Row) -> dict[str, Any]:
    result = dict(row)
    result["metadata_json"] = json.loads(result["metadata_json"] or "{}")
    return result


def _note_row_to_dict(row: aiosqlite.Row) -> dict[str, Any]:
    result = dict(row)
    result["metadata_json"] = json.loads(result["metadata_json"] or "{}")
    return result


def _parse_optional_datetime(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None
