"""Integration tests for FileHandleCenter-backed tools."""

from __future__ import annotations

import io
from pathlib import Path

import openpyxl
import pytest

from chatpilot.files.center import FileHandleCenter
from chatpilot.files.models import FileKind, SourceFetchResult, SourceHandleInput
from chatpilot.files.store import SqliteFileStore
from chatpilot.tools.builtin.document_edit import create_document_edit_tool
from chatpilot.tools.builtin.download_media import create_download_media_tool
from chatpilot.tools.builtin.show_image import create_show_image_tool


def _make_xlsx(rows: list[list]) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


class MockAdapter:
    platform = "line:webric"

    def __init__(self, media_data: bytes) -> None:
        self._media_data = media_data
        self.download_calls = 0
        self.fetch_calls = 0

    async def download_media(self, media_id: str) -> bytes | None:
        self.download_calls += 1
        return self._media_data

    async def fetch_source_file(
        self,
        source: SourceHandleInput,
    ) -> SourceFetchResult | None:
        self.fetch_calls += 1
        return SourceFetchResult(
            data=self._media_data,
            filename=source.filename,
            mime_type=source.mime_type,
        )


class MockR2:
    def __init__(self) -> None:
        self.uploads: list[tuple[bytes, str, str]] = []

    async def upload(self, data: bytes, content_type: str, extension: str) -> str | None:
        self.uploads.append((data, content_type, extension))
        return f"https://r2.example.com/generated.{extension}"


class MockInjector:
    def __init__(self) -> None:
        self.items: list[tuple[str, str, str]] = []

    def add(self, session_id: str, item_type: str, value: str) -> None:
        self.items.append((session_id, item_type, value))


SESSION_CONTEXT = {
    "sdk_session_id": "sid-1",
    "route_id": "line:webric:C123",
    "platform": "line:webric",
    "conversation_id": "C123",
    "chatbot_name": "buddy",
}


@pytest.mark.asyncio
async def test_download_media_uses_canonical_file_record(tmp_path):
    store = SqliteFileStore(str(tmp_path / "files.db"))
    await store.initialize()
    adapter = MockAdapter(b"image-bytes")
    center = FileHandleCenter(store, {adapter.platform: adapter}, asset_root=tmp_path / "assets")
    handle = await center.register(
        SourceHandleInput(
            route_id=SESSION_CONTEXT["route_id"],
            platform=adapter.platform,
            kind=FileKind.image,
            native_locator="img-1",
            filename="photo.jpg",
            mime_type="image/jpeg",
        )
    )
    await center.download_now(handle.file_id)
    adapter.download_calls = 0

    tool = create_download_media_tool({adapter.platform: adapter}, center)
    result = await tool.handler({
        "session_context": SESSION_CONTEXT,
        "arguments": {"ref": "line:webric:img-1"},
    })

    assert result["resultType"] == "success"
    assert f"file_id: {handle.file_id}" in result["textResultForLlm"]
    assert adapter.download_calls == 0

    await store.close()


@pytest.mark.asyncio
async def test_document_edit_generates_governed_output_and_relations(tmp_path):
    store = SqliteFileStore(str(tmp_path / "files.db"))
    await store.initialize()
    adapter = MockAdapter(_make_xlsx([["品名", "數量"], ["水泥漆", 10]]))
    center = FileHandleCenter(store, {adapter.platform: adapter}, asset_root=tmp_path / "assets")
    source = await center.register(
        SourceHandleInput(
            route_id=SESSION_CONTEXT["route_id"],
            platform=adapter.platform,
            kind=FileKind.file,
            native_locator="sheet-1",
            filename="report.xlsx",
            mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    )
    await center.download_now(source.file_id)
    adapter.download_calls = 0

    r2 = MockR2()
    tool = create_document_edit_tool({adapter.platform: adapter}, r2, center)
    result = await tool.handler({
        "session_context": SESSION_CONTEXT,
        "arguments": {
            "file_ref": "line:webric:sheet-1:report.xlsx",
            "instruction": "追加一列",
            "data": '[["乳膠漆", 5]]',
        },
    })

    assert result["resultType"] == "success"
    assert adapter.download_calls == 0
    generated_file_id = result["textResultForLlm"].split("file_id: ", 1)[1].strip()
    generated_handle = await center.get_handle(generated_file_id)
    generated_path = await center.ensure_local(generated_file_id)
    relations = await center.list_relations(from_file_id=generated_file_id)

    assert generated_handle is not None
    assert Path(generated_path).exists()
    assert {relation["relation_type"] for relation in relations} == {
        "derived_from",
        "generated_by_tool",
    }
    assert any(relation["to_file_id"] == source.file_id for relation in relations)

    await store.close()


@pytest.mark.asyncio
async def test_show_image_blocks_ungoverned_internal_file(tmp_path):
    store = SqliteFileStore(str(tmp_path / "files.db"))
    await store.initialize()
    adapter = MockAdapter(b"image-bytes")
    center = FileHandleCenter(store, {adapter.platform: adapter}, asset_root=tmp_path / "assets")
    handle = await center.register_bytes_file(
        route_id=SESSION_CONTEXT["route_id"],
        data=b"internal-image",
        kind=FileKind.image,
        filename="preview.png",
        mime_type="image/png",
    )
    injector = MockInjector()
    tool = create_show_image_tool({adapter.platform: adapter}, MockR2(), injector, center)

    result = await tool.handler({
        "session_id": "sid-1",
        "session_context": SESSION_CONTEXT,
        "arguments": {"file_id": handle.file_id},
    })

    assert result["resultType"] == "failure"
    assert "未被允許" in result["textResultForLlm"]
    assert injector.items == []

    await store.close()


@pytest.mark.asyncio
async def test_show_image_allows_governed_internal_file_and_records_exposure(tmp_path):
    store = SqliteFileStore(str(tmp_path / "files.db"))
    await store.initialize()
    adapter = MockAdapter(b"image-bytes")
    center = FileHandleCenter(store, {adapter.platform: adapter}, asset_root=tmp_path / "assets")
    handle = await center.register_bytes_file(
        route_id=SESSION_CONTEXT["route_id"],
        data=b"internal-image",
        kind=FileKind.image,
        filename="preview.png",
        mime_type="image/png",
        generated_by_tool="vision_render",
    )
    injector = MockInjector()
    tool = create_show_image_tool({adapter.platform: adapter}, MockR2(), injector, center)

    result = await tool.handler({
        "session_id": "sid-1",
        "session_context": SESSION_CONTEXT,
        "arguments": {"file_id": handle.file_id, "caption": "比較圖"},
    })

    relations = await center.list_relations(from_file_id=handle.file_id)

    assert result["resultType"] == "success"
    assert injector.items == [("sid-1", "image", "https://r2.example.com/generated.png")]
    assert any(relation["relation_type"] == "shown_in_response" for relation in relations)

    await store.close()
