"""Tests for show_image tool ref parsing."""

from pathlib import Path

import pytest

from chatpilot.files.center import FileHandleCenter
from chatpilot.files.models import FileKind, SourceFetchResult, SourceHandleInput
from chatpilot.files.store import SqliteFileStore
from chatpilot.tools.builtin.show_image import create_show_image_tool


class MockAdapter:
    def __init__(self) -> None:
        self.download_calls = 0

    async def download_media(self, media_id: str) -> bytes | None:
        self.download_calls += 1
        assert media_id == "img_123"
        return b"fake-image"

    async def fetch_source_file(
        self,
        source: SourceHandleInput,
    ) -> SourceFetchResult | None:
        return SourceFetchResult(
            data=b"fake-image",
            filename=source.filename,
            mime_type=source.mime_type or "image/jpeg",
        )


class MockR2:
    async def upload(self, data: bytes, content_type: str, extension: str) -> str | None:
        assert data == b"fake-image"
        assert content_type == "image/jpeg"
        assert extension == "jpg"
        return "https://r2.example.com/img.jpg"


class MockInjector:
    def __init__(self) -> None:
        self.items: list[tuple[str, str, str]] = []

    def add(self, session_id: str, item_type: str, value: str) -> None:
        self.items.append((session_id, item_type, value))


@pytest.mark.asyncio
async def test_show_image_accepts_multi_part_platform_ref():
    injector = MockInjector()
    adapter = MockAdapter()
    tool = create_show_image_tool(
        {"line:webric": adapter},
        MockR2(),
        injector,
    )

    result = await tool.handler({
        "session_id": "sid-1",
        "arguments": {"ref": "line:webric:img_123"},
    })

    assert result["resultType"] == "success"
    assert injector.items == [("sid-1", "image", "https://r2.example.com/img.jpg")]
    assert adapter.download_calls == 1


@pytest.mark.asyncio
async def test_show_image_prefers_center_lookup_when_session_context_present(tmp_path):
    injector = MockInjector()
    adapter = MockAdapter()
    store = SqliteFileStore(str(tmp_path / "files.db"))
    await store.initialize()
    center = FileHandleCenter(
        store,
        {"line:webric": adapter},
        asset_root=tmp_path / "assets",
    )
    handle = await center.register(
        SourceHandleInput(
            route_id="line:webric:C123",
            platform="line:webric",
            kind=FileKind.image,
            native_locator="img_123",
            filename="photo.jpg",
            mime_type="image/jpeg",
        )
    )
    await center.download_now(handle.file_id)
    adapter.download_calls = 0

    tool = create_show_image_tool(
        {"line:webric": adapter},
        MockR2(),
        injector,
        center,
    )

    result = await tool.handler({
        "session_id": "sid-1",
        "session_context": {
            "sdk_session_id": "sid-1",
            "route_id": "line:webric:C123",
            "platform": "line:webric",
            "conversation_id": "C123",
            "chatbot_name": "buddy",
        },
        "arguments": {"ref": "line:webric:img_123"},
    })

    assert result["resultType"] == "success"
    assert injector.items == [("sid-1", "image", "https://r2.example.com/img.jpg")]
    assert adapter.download_calls == 0
    assert Path(await center.ensure_local(handle.file_id)).exists()

    await store.close()
