"""Tests for multi-line webhook dispatch."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from chatpilot.core.errors import AdapterError
from chatpilot.core.types import Message
from chatpilot.hub.context_buffer import ContextBuffer
from chatpilot.hub.hub import _AUDIO_REF_PATTERN, InMemoryMessageHub
from chatpilot.server.webhook import router
from chatpilot.tools.builtin.download_media import create_download_media_tool


class _StubHub:
    def __init__(self) -> None:
        self.received: list[tuple[Message, object]] = []

    async def receive(self, message: Message, adapter: object) -> None:
        self.received.append((message, adapter))


class _StubLineAdapter:
    def __init__(self, platform: str, valid_signature: str) -> None:
        self._platform = platform
        self._valid_signature = valid_signature
        self.verify_calls = 0

    @property
    def platform(self) -> str:
        return self._platform

    async def verify_request(self, request) -> bool:
        self.verify_calls += 1
        signature = request.headers.get("X-Line-Signature", "")
        if signature != self._valid_signature:
            raise AdapterError("invalid signature", code="SIGNATURE_INVALID")
        return True

    async def parse_messages(self, request) -> list[Message]:
        return [
            Message(
                text="hello",
                user_id="U1",
                platform=self._platform,
                group_id="C1",
                conversation_id="C1",
                is_mention=True,
            )
        ]

    async def send_reply(self, message, response) -> None:
        return None

    async def push_message(self, route_id, response) -> None:
        return None

    async def download_media(self, media_id: str) -> bytes | None:
        return b"ok"


def _build_test_client(adapters: dict[str, object]) -> tuple[TestClient, _StubHub]:
    app = FastAPI()
    app.include_router(router)
    hub = _StubHub()
    app.state.adapters = adapters
    app.state.hub = hub
    return TestClient(app), hub


def test_webhook_line_dispatches_to_matching_named_adapter():
    adapter_a = _StubLineAdapter("line:webric", "sig-a")
    adapter_b = _StubLineAdapter("line:shinyipaint", "sig-b")
    client, hub = _build_test_client({
        "line:webric": adapter_a,
        "line:shinyipaint": adapter_b,
        "mock": SimpleNamespace(),
    })

    response = client.post(
        "/webhook/line",
        content=b'{"events":[]}',
        headers={"X-Line-Signature": "sig-b"},
    )

    assert response.status_code == 200
    assert adapter_a.verify_calls == 1
    assert adapter_b.verify_calls == 1
    assert [msg.platform for msg, _ in hub.received] == ["line:shinyipaint"]


def test_webhook_line_returns_401_when_no_named_adapter_matches():
    client, hub = _build_test_client({
        "line:webric": _StubLineAdapter("line:webric", "sig-a"),
        "line:shinyipaint": _StubLineAdapter("line:shinyipaint", "sig-b"),
    })

    response = client.post(
        "/webhook/line",
        content=b'{"events":[]}',
        headers={"X-Line-Signature": "sig-miss"},
    )

    assert response.status_code == 401
    assert hub.received == []


@pytest.mark.asyncio
async def test_download_media_accepts_multi_part_platform_key():
    adapter = _StubLineAdapter("line:webric", "sig-a")
    tool = create_download_media_tool({"line:webric": adapter})

    result = await tool.handler({"arguments": {"ref": "line:webric:img123"}})

    assert result["resultType"] == "success"


@pytest.mark.asyncio
async def test_hub_push_uses_full_platform_key():
    adapter = _StubLineAdapter("line:webric", "sig-a")
    pushed: list[str] = []

    async def fake_push(route_id, response):
        pushed.append(route_id)

    adapter.push_message = fake_push
    hub = InMemoryMessageHub(
        context_buffer=ContextBuffer(),
        adapters={"line:webric": adapter},
    )

    await hub.push("line:webric:C123", SimpleNamespace(text="ok"))

    assert pushed == ["line:webric:C123"]


def test_audio_ref_pattern_matches_multi_line_platform():
    match = _AUDIO_REF_PATTERN.search("[音檔 ref:line:webric:12345]")

    assert match is not None
    assert match.group(1) == "line:webric"
    assert match.group(2) == "12345"
