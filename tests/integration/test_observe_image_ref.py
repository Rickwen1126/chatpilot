from __future__ import annotations

from pathlib import Path

import pytest

from chatpilot.files.center import FileHandleCenter
from chatpilot.files.models import FileKind, SourceFetchResult, SourceHandleInput
from chatpilot.files.store import SqliteFileStore
from chatpilot.tools.builtin.observe_image_ref import create_observe_image_ref_tool


class _FakeAdapter:
    async def fetch_source_file(
        self,
        source: SourceHandleInput,
    ) -> SourceFetchResult | None:
        return SourceFetchResult(
            data=b"fake-image-bytes",
            filename=source.filename,
            mime_type=source.mime_type or "image/jpeg",
        )


class _FakeSession:
    def __init__(self, seen: dict) -> None:
        self._seen = seen

    async def send_and_wait_with_attachments(
        self,
        message: str,
        *,
        attachments: list[dict[str, str]],
        timeout: float = 60.0,
    ) -> str:
        self._seen["message"] = message
        self._seen["attachments"] = attachments
        self._seen["timeout"] = timeout
        return "圖片顯示兩桶白漆放在地上。"

    async def destroy(self) -> None:
        self._seen["destroyed"] = True


class _FakeSdkClient:
    def __init__(self, seen: dict) -> None:
        self._seen = seen

    async def create_session(self, session_id: str, **kwargs):
        self._seen["session_id"] = session_id
        self._seen["model"] = kwargs.get("model")
        self._seen["system_message"] = kwargs.get("system_message")
        self._seen["tools"] = kwargs.get("tools")
        return _FakeSession(self._seen)


@pytest.mark.asyncio
async def test_observe_image_ref_uses_local_attachment_and_returns_text(tmp_path):
    store = SqliteFileStore(str(tmp_path / "files.db"))
    await store.initialize()
    adapter = _FakeAdapter()
    center = FileHandleCenter(
        store,
        {"line:demo": adapter},
        asset_root=tmp_path / "assets",
    )
    handle = await center.register(
        SourceHandleInput(
            route_id="line:demo:C123",
            platform="line:demo",
            kind=FileKind.image,
            native_locator="img123",
            filename="photo.jpg",
            mime_type="image/jpeg",
        )
    )
    await center.download_now(handle.file_id)

    seen: dict = {}
    tool = create_observe_image_ref_tool(
        _FakeSdkClient(seen),
        {"line:demo": adapter},
        center,
    )

    result = await tool.handler(
        {
            "session_context": {
                "sdk_session_id": "observer-abc",
                "route_id": "line:demo:C123",
                "platform": "line:demo",
                "conversation_id": "C123",
                "chatbot_name": "observer",
            },
            "arguments": {"image_ref": "line:demo:img123"},
        }
    )

    assert result["resultType"] == "success"
    assert "兩桶白漆" in result["textResultForLlm"]
    assert seen["attachments"] and seen["attachments"][0]["type"] == "file"
    assert Path(seen["attachments"][0]["path"]).exists()
    assert seen["tools"] is None
    assert seen["destroyed"] is True

    await store.close()
