"""Unit tests for FileHandleCenter."""

from __future__ import annotations

from pathlib import Path

import pytest

from chatpilot.files.center import FileHandleCenter
from chatpilot.files.models import FileKind, SourceFetchResult, SourceHandleInput
from chatpilot.files.store import SqliteFileStore


class _FakeAdapter:
    def __init__(self, platform: str = "line:webric") -> None:
        self._platform = platform
        self.fetch_calls: list[SourceHandleInput] = []

    @property
    def platform(self) -> str:
        return self._platform

    def build_source_handle(self, **kwargs) -> SourceHandleInput:
        return SourceHandleInput(platform=self._platform, **kwargs)

    async def fetch_source_file(
        self,
        source: SourceHandleInput,
    ) -> SourceFetchResult | None:
        self.fetch_calls.append(source)
        return SourceFetchResult(
            data=b"file-bytes",
            filename=source.filename,
            mime_type=source.mime_type or "application/octet-stream",
        )


@pytest.mark.asyncio
async def test_register_and_download_now_materializes_local_asset(tmp_path):
    store = SqliteFileStore(str(tmp_path / "files.db"))
    await store.initialize()
    adapter = _FakeAdapter()
    center = FileHandleCenter(
        store,
        {adapter.platform: adapter},
        asset_root=tmp_path / "assets",
    )

    source = SourceHandleInput(
        route_id="line:webric:C123",
        platform=adapter.platform,
        kind=FileKind.file,
        native_locator="file-123",
        filename="report.txt",
        mime_type="text/plain",
    )

    handle = await center.register(source)
    asset = await center.download_now(handle.file_id)

    assert Path(asset.local_path).exists()
    assert Path(asset.local_path).read_bytes() == b"file-bytes"
    assert adapter.fetch_calls[0].native_locator == "file-123"

    stored = await store.get_file(handle.file_id)
    assert stored["storage_backend"] == "local"
    assert stored["fetch_status"] == "ready"
    assert stored["size_bytes"] == len(b"file-bytes")

    await store.close()


@pytest.mark.asyncio
async def test_ensure_local_reuses_existing_materialized_asset(tmp_path):
    store = SqliteFileStore(str(tmp_path / "files.db"))
    await store.initialize()
    adapter = _FakeAdapter()
    center = FileHandleCenter(
        store,
        {adapter.platform: adapter},
        asset_root=tmp_path / "assets",
    )

    handle = await center.register(
        SourceHandleInput(
            route_id="line:webric:C123",
            platform=adapter.platform,
            kind=FileKind.audio,
            native_locator="audio-123",
            filename="audio.m4a",
            mime_type="audio/m4a",
        )
    )

    first_path = await center.ensure_local(handle.file_id)
    second_path = await center.ensure_local(handle.file_id)

    assert first_path == second_path
    assert len(adapter.fetch_calls) == 1

    await store.close()


@pytest.mark.asyncio
async def test_cleanup_expired_removes_local_asset_but_keeps_row(tmp_path):
    store = SqliteFileStore(str(tmp_path / "files.db"))
    await store.initialize()
    adapter = _FakeAdapter()
    center = FileHandleCenter(
        store,
        {adapter.platform: adapter},
        asset_root=tmp_path / "assets",
    )

    handle = await center.register(
        SourceHandleInput(
            route_id="line:webric:C123",
            platform=adapter.platform,
            kind=FileKind.image,
            native_locator="image-123",
        )
    )
    await center.download_now(handle.file_id)
    await store.update_file(handle.file_id, expires_at="2000-01-01T00:00:00+00:00")

    cleaned = await center.cleanup_expired()
    stored = await store.get_file(handle.file_id)

    assert cleaned == 1
    assert stored is not None
    assert stored["fetch_status"] == "expired"
    assert stored["storage_backend"] == "none"
    assert stored["local_path"] is None

    await store.close()
