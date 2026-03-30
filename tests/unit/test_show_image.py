"""Tests for show_image tool ref parsing."""

import pytest

from chatpilot.tools.builtin.show_image import create_show_image_tool


class MockAdapter:
    async def download_media(self, media_id: str) -> bytes | None:
        assert media_id == "img_123"
        return b"fake-image"


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
    tool = create_show_image_tool(
        {"line:webric": MockAdapter()},
        MockR2(),
        injector,
    )

    result = await tool.handler({
        "session_id": "sid-1",
        "arguments": {"ref": "line:webric:img_123"},
    })

    assert result["resultType"] == "success"
    assert injector.items == [("sid-1", "image", "https://r2.example.com/img.jpg")]
