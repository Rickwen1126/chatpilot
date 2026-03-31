"""Vision integration tests for local attachment delivery."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from chatpilot.files.center import FileHandleCenter
from chatpilot.files.models import FileKind, SourceFetchResult, SourceHandleInput
from chatpilot.files.store import SqliteFileStore
from chatpilot.pipeline.samples.batch_vision import BatchImageVisionNode


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
        return "vision ok"

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
async def test_batch_vision_uses_local_file_attachments(tmp_path):
    store = SqliteFileStore(str(tmp_path / "files.db"))
    await store.initialize()
    adapter = _FakeAdapter()
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
            native_locator="img123",
            filename="photo.jpg",
            mime_type="image/jpeg",
        )
    )
    await center.download_now(handle.file_id)

    seen: dict = {}
    node = BatchImageVisionNode(
        _FakeSdkClient(seen),
        tool_factory=SimpleNamespace(),
        file_handle_center=center,
        adapters={"line:webric": adapter},
    )

    result = await node.execute({
        "route_id": "line:webric:C123",
        "refs": ["line:webric:img123"],
        "prompt": "分析照片",
    })

    assert result.status == "success"
    assert result.data["analysis"] == "vision ok"
    assert seen["attachments"] and seen["attachments"][0]["type"] == "file"
    assert seen["attachments"][0]["path"].endswith("source.bin")
    assert seen["tools"] is None
    assert seen["destroyed"] is True

    await store.close()


@pytest.mark.asyncio
async def test_batch_vision_errors_when_canonical_file_missing(tmp_path):
    store = SqliteFileStore(str(tmp_path / "files.db"))
    await store.initialize()
    adapter = _FakeAdapter()
    node = BatchImageVisionNode(
        _FakeSdkClient({}),
        tool_factory=SimpleNamespace(),
        file_handle_center=FileHandleCenter(
            store,
            {"line:webric": adapter},
            asset_root=tmp_path / "assets",
        ),
        adapters={"line:webric": adapter},
    )

    result = await node.execute({
        "route_id": "line:webric:C123",
        "refs": ["line:webric:img404"],
    })

    assert result.status == "error"
    assert "missing canonical file" in (result.error or "")

    await store.close()
