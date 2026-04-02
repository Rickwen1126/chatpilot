"""Tests for multi-line webhook dispatch."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from chatpilot.core.errors import AdapterError
from chatpilot.core.types import Message
from chatpilot.files.center import FileHandleCenter
from chatpilot.files.models import FileKind, SourceFetchResult, SourceHandleInput
from chatpilot.files.store import SqliteFileStore
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

    async def fetch_source_file(
        self,
        source: SourceHandleInput,
    ) -> SourceFetchResult | None:
        return SourceFetchResult(
            data=b"ok",
            filename=source.filename,
            mime_type=source.mime_type,
        )


def _build_test_client(adapters: dict[str, object]) -> tuple[TestClient, _StubHub]:
    app = FastAPI()
    app.include_router(router)
    hub = _StubHub()
    app.state.adapters = adapters
    app.state.hub = hub
    return TestClient(app), hub


class _StubLineSyncApi:
    def get_group_summary(self, conversation_id: str):
        assert conversation_id == "C123"
        return SimpleNamespace(group_name="Bot 測試群")

    def get_group_member_count(self, conversation_id: str):
        assert conversation_id == "C123"
        return SimpleNamespace(count=4)

    def get_profile(self, conversation_id: str):
        assert conversation_id == "U123"
        return SimpleNamespace(display_name="Rick")


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


def test_webhook_line_logs_error_when_legacy_adapter_selected(caplog):
    client, hub = _build_test_client({
        "line": _StubLineAdapter("line", "sig-legacy"),
    })

    with caplog.at_level("ERROR"):
        response = client.post(
            "/webhook/line",
            content=b'{"events":[]}',
            headers={"X-Line-Signature": "sig-legacy"},
        )

    assert response.status_code == 200
    assert [msg.platform for msg, _ in hub.received] == ["line"]
    assert "Legacy unnamed LINE adapter selected for webhook dispatch" in caplog.text


@pytest.mark.asyncio
async def test_download_media_accepts_multi_part_platform_key():
    adapter = _StubLineAdapter("line:webric", "sig-a")
    tool = create_download_media_tool({"line:webric": adapter})

    result = await tool.handler({"arguments": {"ref": "line:webric:img123"}})

    assert result["resultType"] == "success"


@pytest.mark.asyncio
async def test_download_media_prefers_center_lookup_for_legacy_ref(tmp_path):
    adapter = _StubLineAdapter("line:webric", "sig-a")
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
            native_locator="img123",
            filename="photo.jpg",
            mime_type="image/jpeg",
        )
    )
    await center.download_now(handle.file_id)
    tool = create_download_media_tool({"line:webric": adapter}, center)

    result = await tool.handler({
        "session_id": "sid-1",
        "session_context": {
            "sdk_session_id": "sid-1",
            "route_id": "line:webric:C123",
            "platform": "line:webric",
            "conversation_id": "C123",
            "chatbot_name": "buddy",
        },
        "arguments": {"ref": "line:webric:img123"},
    })

    assert result["resultType"] == "success"
    assert handle.file_id in result["textResultForLlm"]

    await store.close()


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


def test_cli_routes_sync_syncs_line_group_and_user_labels(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    contexts = [
        SimpleNamespace(
            route_id="line:shinyipaint:C123",
            platform="line:shinyipaint",
            conversation_id="C123",
        ),
        SimpleNamespace(
            route_id="line:shinyipaint:U123",
            platform="line:shinyipaint",
            conversation_id="U123",
        ),
    ]
    monkeypatch.setattr(
        "chatpilot.server.webhook._load_known_session_contexts",
        lambda request: contexts,
    )

    adapter = SimpleNamespace(_api=_StubLineSyncApi())
    client, _ = _build_test_client({"line:shinyipaint": adapter})

    response = client.post("/cli/routes/sync")

    assert response.status_code == 200
    assert response.json() == {
        "synced": [
            {
                "route_id": "line:shinyipaint:C123",
                "label": "Bot 測試群（4人）",
            },
            {
                "route_id": "line:shinyipaint:U123",
                "label": "Rick（私訊）",
            },
        ],
        "total": 2,
    }
    labels = (tmp_path / "data" / "route_labels.json").read_text(encoding="utf-8")
    assert '"line:shinyipaint:C123": "Bot 測試群（4人）"' in labels
    assert '"line:shinyipaint:U123": "Rick（私訊）"' in labels
