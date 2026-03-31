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


@pytest.mark.asyncio
async def test_route_lookup_and_notes_survive_asset_expiry(tmp_path):
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
            route_id="line:webric:C999",
            platform=adapter.platform,
            kind=FileKind.image,
            native_locator="img-999",
            filename="photo.jpg",
            mime_type="image/jpeg",
        )
    )
    await center.download_now(handle.file_id)
    await center.add_note(
        handle.file_id,
        note_type="summary",
        content="昨天那張圖偏暗，但構圖不錯。",
        created_by="vision-agent",
    )
    await store.update_file(handle.file_id, expires_at="2000-01-01T00:00:00+00:00")

    cleaned = await center.cleanup_expired()
    route_files = await center.list_route_files("line:webric:C999")
    notes = await center.list_notes(handle.file_id)

    assert cleaned == 1
    assert route_files[0]["file_id"] == handle.file_id
    assert route_files[0]["fetch_status"] == "expired"
    assert notes == [{
        "note_id": notes[0]["note_id"],
        "file_id": handle.file_id,
        "note_type": "summary",
        "content": "昨天那張圖偏暗，但構圖不錯。",
        "metadata_json": {},
        "created_at": notes[0]["created_at"],
        "created_by": "vision-agent",
    }]

    await store.close()


@pytest.mark.asyncio
async def test_register_local_file_creates_governed_asset_and_relations(tmp_path):
    store = SqliteFileStore(str(tmp_path / "files.db"))
    await store.initialize()
    adapter = _FakeAdapter()
    center = FileHandleCenter(
        store,
        {adapter.platform: adapter},
        asset_root=tmp_path / "assets",
    )

    source_handle = await center.register(
        SourceHandleInput(
            route_id="line:webric:C777",
            platform=adapter.platform,
            kind=FileKind.file,
            native_locator="source-777",
            filename="source.xlsx",
        )
    )

    generated_path = tmp_path / "generated.xlsx"
    generated_path.write_bytes(b"excel-bytes")

    generated_handle = await center.register_local_file(
        route_id="line:webric:C777",
        local_path=generated_path,
        kind=FileKind.file,
        filename="整理後.xlsx",
        mime_type=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
        derived_from_file_id=source_handle.file_id,
        generated_by_tool="document_edit",
    )

    local_path = await center.ensure_local(generated_handle.file_id)
    relations = await center.list_relations(from_file_id=generated_handle.file_id)

    assert Path(local_path).read_bytes() == b"excel-bytes"
    assert {relation["relation_type"] for relation in relations} == {
        "derived_from",
        "generated_by_tool",
    }
    assert any(relation["to_file_id"] == source_handle.file_id for relation in relations)
    assert any(relation["subject_id"] == "document_edit" for relation in relations)

    await store.close()


@pytest.mark.asyncio
async def test_register_bytes_file_creates_governed_asset_and_relations(tmp_path):
    store = SqliteFileStore(str(tmp_path / "files.db"))
    await store.initialize()
    center = FileHandleCenter(
        store,
        {},
        asset_root=tmp_path / "assets",
    )

    handle = await center.register_bytes_file(
        route_id="line:webric:C888",
        data=b"generated-bytes",
        kind=FileKind.file,
        filename="整理後.xlsx",
        mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        generated_by_tool="document_edit",
    )

    local_path = await center.ensure_local(handle.file_id)
    relations = await center.list_relations(from_file_id=handle.file_id)

    assert Path(local_path).read_bytes() == b"generated-bytes"
    assert {relation["relation_type"] for relation in relations} == {
        "generated_by_tool",
    }
    assert relations[0]["subject_id"] == "document_edit"

    await store.close()
