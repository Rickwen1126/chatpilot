"""Integration tests for file ingress preprocessing and STT handoff."""

from __future__ import annotations

from pathlib import Path

import pytest

from chatpilot.core.types import Message
from chatpilot.files.center import FileHandleCenter
from chatpilot.files.ingress import InboundFilePreprocessor
from chatpilot.files.models import FileKind, SourceFetchResult, SourceHandleInput
from chatpilot.files.store import SqliteFileStore
from chatpilot.hub.context_buffer import ContextBuffer
from chatpilot.hub.hub import InMemoryMessageHub


class _FakeAdapter:
    def __init__(self, platform: str = "line:webric") -> None:
        self._platform = platform
        self.fetch_calls: list[SourceHandleInput] = []

    @property
    def platform(self) -> str:
        return self._platform

    @property
    def format_hint(self) -> str | None:
        return None

    async def fetch_source_file(
        self,
        source: SourceHandleInput,
    ) -> SourceFetchResult | None:
        self.fetch_calls.append(source)
        return SourceFetchResult(
            data=b"audio-bytes" if source.kind == FileKind.audio else b"image-bytes",
            filename=source.filename,
            mime_type=source.mime_type or "application/octet-stream",
        )


class _FakeStt:
    enabled = True

    def __init__(self) -> None:
        self.calls: list[tuple[bytes, str]] = []

    async def transcribe(
        self,
        audio_bytes: bytes,
        language: str = "zh",
        filename: str = "audio.m4a",
    ) -> str | None:
        self.calls.append((audio_bytes, filename))
        return "這是轉錄內容"


@pytest.mark.asyncio
async def test_file_ingress_registers_handles_and_eager_downloads_audio(tmp_path):
    store = SqliteFileStore(str(tmp_path / "files.db"))
    await store.initialize()
    adapter = _FakeAdapter()
    center = FileHandleCenter(
        store,
        {adapter.platform: adapter},
        asset_root=tmp_path / "assets",
    )
    ingress = InboundFilePreprocessor(center)

    message = Message(
        text="[音檔 ref:line:webric:audio-123]",
        user_id="U123",
        user_name="Rick",
        platform=adapter.platform,
        conversation_id="U123",
        source_handles=[
            SourceHandleInput(
                route_id="line:webric:U123",
                platform=adapter.platform,
                kind=FileKind.audio,
                native_locator="audio-123",
                filename="audio.m4a",
            )
        ],
    )

    message = await ingress.process(message, adapter)

    assert len(message.file_handles) == 1
    assert len(adapter.fetch_calls) == 1
    file_id = message.file_handles[0].file_id
    asset = await center.get_asset(file_id)
    assert asset is not None
    assert asset.local_path is not None
    assert Path(asset.local_path).exists()
    assert message.platform_context["file_ids"] == [file_id]

    await store.close()


@pytest.mark.asyncio
async def test_hub_transcribes_audio_from_canonical_local_asset(tmp_path):
    store = SqliteFileStore(str(tmp_path / "files.db"))
    await store.initialize()
    adapter = _FakeAdapter()
    center = FileHandleCenter(
        store,
        {adapter.platform: adapter},
        asset_root=tmp_path / "assets",
    )
    ingress = InboundFilePreprocessor(center)
    stt = _FakeStt()
    hub = InMemoryMessageHub(
        context_buffer=ContextBuffer(),
        adapters={adapter.platform: adapter},
        stt_transcriber=stt,
        file_ingress=ingress,
        file_handle_center=center,
    )

    message = Message(
        text="[音檔 ref:line:webric:audio-123]",
        user_id="U123",
        user_name="Rick",
        platform=adapter.platform,
        conversation_id="U123",
        source_handles=[
            SourceHandleInput(
                route_id="line:webric:U123",
                platform=adapter.platform,
                kind=FileKind.audio,
                native_locator="audio-123",
                filename="audio.m4a",
            )
        ],
    )

    await hub.receive(message, adapter)

    assert stt.calls == [(b"audio-bytes", "audio.m4a")]
    assert "轉錄：這是轉錄內容" in message.text
    assert len(adapter.fetch_calls) == 1

    await store.close()
