"""Tests for multi-line webhook dispatch."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from chatpilot.core.config import GatewayConfig
from chatpilot.core.errors import AdapterError
from chatpilot.core.types import (
    DiscoveryEvent,
    MatchWeights,
    Message,
    RouteOnboardingState,
    SessionContext,
)
from chatpilot.files.center import FileHandleCenter
from chatpilot.files.models import FileKind, SourceFetchResult, SourceHandleInput
from chatpilot.files.store import SqliteFileStore
from chatpilot.hub.context_buffer import ContextBuffer
from chatpilot.hub.hub import _AUDIO_REF_PATTERN, InMemoryMessageHub
from chatpilot.routing.onboarding import RouteOnboardingRegistry
from chatpilot.routing.router import BindingRouter
from chatpilot.server.webhook import router
from chatpilot.tools.builtin.download_media import create_download_media_tool
from chatpilot.tools.session_context import SessionContextRegistry


class _StubHub:
    def __init__(self) -> None:
        self.received: list[tuple[Message, object]] = []
        self.route_policies: dict[str, dict] = {}
        self.captures: list[tuple[str, int, list[str]]] = []

    async def receive(self, message: Message, adapter: object) -> None:
        self.received.append((message, adapter))

    def register_route_policy(
        self,
        route_id: str,
        *,
        reply_policy: str,
        processing_policy: str,
        capture_enabled: bool,
    ) -> None:
        self.route_policies[route_id] = {
            "reply_policy": reply_policy,
            "processing_policy": processing_policy,
            "capture_enabled": capture_enabled,
        }

    def register_capture(
        self, route_id: str, batch_size: int, categories: list[str]
    ) -> None:
        self.captures.append((route_id, batch_size, categories))


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


def _build_test_client(
    adapters: dict[str, object],
    *,
    config: GatewayConfig | None = None,
    binding_router: BindingRouter | None = None,
    chatbot_manager: object | None = None,
    onboarding_registry: RouteOnboardingRegistry | None = None,
    session_context_registry: SessionContextRegistry | None = None,
) -> tuple[TestClient, _StubHub]:
    app = FastAPI()
    app.include_router(router)
    hub = _StubHub()
    app.state.adapters = adapters
    app.state.hub = hub
    app.state.config = config or GatewayConfig()
    app.state.binding_router = binding_router or BindingRouter([], MatchWeights())
    app.state.chatbot_manager = chatbot_manager or SimpleNamespace(
        get_current_chatbot=lambda route_id: None,
        get_configured_model=lambda chatbot: None,
        get_effective_model=lambda route_id, chatbot: None,
        get_session=lambda route_id: None,
    )
    app.state.route_onboarding_registry = onboarding_registry or RouteOnboardingRegistry()
    app.state.session_context_registry = session_context_registry or SessionContextRegistry()
    app.state.observation_groups = {}
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


def test_webhook_line_follow_discovery_materializes_onboarding_state(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    class _DiscoveryLineAdapter(_StubLineAdapter):
        async def parse_messages(self, request) -> list[Message]:
            return []

        async def parse_discovery_events(self, request) -> list[DiscoveryEvent]:
            return [
                DiscoveryEvent(
                    discovery_type="follow",
                    route_type="user",
                    platform=self.platform,
                    conversation_id="U123",
                )
            ]

        def get_route_label(self, conversation_id: str) -> str | None:
            assert conversation_id == "U123"
            return "Rick（私訊）"

    config = GatewayConfig(
        discovery_profiles={
            "default_private": {
                "chatbot": "buddy",
                "reply_policy": "addressed",
                "processing_policy": "interactive",
            }
        },
        discovery_rules=[
            {
                "platform": "line:shinyipaint",
                "route_type": "user",
                "profile": "default_private",
            }
        ],
        chatbots={
            "buddy": {
                "name": "buddy",
                "model": "gpt-5.4-mini",
                "system_message": "test",
            }
        },
    )
    registry = RouteOnboardingRegistry()
    client, hub = _build_test_client(
        {
            "line:shinyipaint": _DiscoveryLineAdapter("line:shinyipaint", "sig-b"),
        },
        config=config,
        onboarding_registry=registry,
    )

    response = client.post(
        "/webhook/line",
        content=b'{"events":[]}',
        headers={"X-Line-Signature": "sig-b"},
    )

    assert response.status_code == 200
    assert hub.received == []
    state = registry.resolve("line:shinyipaint:U123")
    assert state is not None
    assert state.chatbot == "buddy"
    assert state.label == "Rick（私訊）"
    assert hub.route_policies["line:shinyipaint:U123"] == {
        "reply_policy": "addressed",
        "processing_policy": "interactive",
        "capture_enabled": False,
    }


def test_cli_routes_includes_discovered_routes_without_sessions(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    registry = RouteOnboardingRegistry()
    registry.register(
        RouteOnboardingState(
            route_id="line:shinyipaint:C123",
            platform="line:shinyipaint",
            conversation_id="C123",
            route_type="group",
            chatbot="buddy",
            reply_policy="never",
            processing_policy="none",
            observation=None,
            label="Bot 測試群",
            profile_name="default_group_safe",
            discovery_type="join",
            discovered_at=datetime(2026, 4, 7, tzinfo=timezone.utc),
        )
    )
    client, _ = _build_test_client(
        {},
        onboarding_registry=registry,
    )

    response = client.get("/cli/routes")

    assert response.status_code == 200
    assert response.json()["routes"] == [
        {
            "route_id": "line:shinyipaint:C123",
            "label": "Bot 測試群",
            "platform": "line:shinyipaint",
            "conversation_id": "C123",
            "current_chatbot": "buddy",
            "override": None,
            "default_binding": None,
            "configured_model": None,
            "effective_model": None,
            "session_model": None,
            "sdk_current_model": None,
            "sessions": [],
            "discovered_profile": "default_group_safe",
            "reply_policy": "never",
            "processing_policy": "none",
        }
    ]


def test_cli_routes_merges_discovered_metadata_for_known_session_route(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    registry = RouteOnboardingRegistry()
    registry.register(
        RouteOnboardingState(
            route_id="line:shinyipaint:U123",
            platform="line:shinyipaint",
            conversation_id="U123",
            route_type="user",
            chatbot="buddy",
            reply_policy="addressed",
            processing_policy="interactive",
            observation=None,
            label="Rick（私訊）",
            profile_name="default_private_cheap",
            discovery_type="follow",
            discovered_at=datetime(2026, 4, 7, tzinfo=timezone.utc),
        )
    )
    session_registry = SessionContextRegistry(metadata_dir=tmp_path / "ctx")
    session_registry.register(
        SessionContext(
            sdk_session_id="line-shinyipaint-U123__buddy",
            route_id="line:shinyipaint:U123",
            platform="line:shinyipaint",
            conversation_id="U123",
            chatbot_name="buddy",
        )
    )
    client, _ = _build_test_client(
        {},
        onboarding_registry=registry,
        session_context_registry=session_registry,
    )

    response = client.get("/cli/routes")

    assert response.status_code == 200
    assert response.json()["routes"] == [
        {
            "route_id": "line:shinyipaint:U123",
            "label": "Rick（私訊）",
            "platform": "line:shinyipaint",
            "conversation_id": "U123",
            "current_chatbot": "buddy",
            "override": None,
            "default_binding": None,
            "configured_model": None,
            "effective_model": None,
            "session_model": None,
            "sdk_current_model": None,
            "sessions": ["buddy"],
            "discovered_profile": "default_private_cheap",
            "reply_policy": "addressed",
            "processing_policy": "interactive",
        }
    ]


def test_webhook_line_discovery_falls_back_to_builtin_default_when_no_rule_matches(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)

    class _DiscoveryLineAdapter(_StubLineAdapter):
        async def parse_messages(self, request) -> list[Message]:
            return []

        async def parse_discovery_events(self, request) -> list[DiscoveryEvent]:
            return [
                DiscoveryEvent(
                    discovery_type="join",
                    route_type="group",
                    platform=self.platform,
                    conversation_id="C999",
                )
            ]

        def get_route_label(self, conversation_id: str) -> str | None:
            assert conversation_id == "C999"
            return "未配置群組"

    config = GatewayConfig(
        chatbots={
            "buddy": {
                "name": "buddy",
                "model": "gpt-5.4-mini",
                "system_message": "test",
            }
        }
    )
    registry = RouteOnboardingRegistry()
    client, hub = _build_test_client(
        {
            "line:shinyipaint": _DiscoveryLineAdapter("line:shinyipaint", "sig-c"),
        },
        config=config,
        onboarding_registry=registry,
    )

    response = client.post(
        "/webhook/line",
        content=b'{"events":[]}',
        headers={"X-Line-Signature": "sig-c"},
    )

    assert response.status_code == 200
    state = registry.resolve("line:shinyipaint:C999")
    assert state is not None
    assert state.profile_name == "_builtin_group_default"
    assert state.chatbot == "buddy"
    assert hub.route_policies["line:shinyipaint:C999"] == {
        "reply_policy": "never",
        "processing_policy": "none",
        "capture_enabled": False,
    }


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
