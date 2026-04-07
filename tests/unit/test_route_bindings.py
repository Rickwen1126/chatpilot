from __future__ import annotations

from datetime import datetime, timezone

from chatpilot.core.route_bindings import (
    RouteBindingEntry,
    RouteBindingService,
    load_route_bindings,
)
from chatpilot.core.types import RouteOnboardingState


def test_route_binding_service_upserts_discovered_exact_binding(tmp_path):
    path = tmp_path / "route_bindings.yaml"
    service = RouteBindingService(path)
    service.load()

    state = RouteOnboardingState(
        route_id="line:demo:C123",
        platform="line:demo",
        conversation_id="C123",
        route_type="group",
        chatbot="buddy",
        reply_policy="never",
        processing_policy="none",
        observation=None,
        label="測試群組",
        profile_name="default_group_safe",
        discovery_type="join",
        discovered_at=datetime(2026, 4, 7, tzinfo=timezone.utc),
    )

    entry = service.upsert_from_onboarding(state)
    service.save()

    assert entry.match == {"platform": "line:demo", "group_id": "C123"}
    assert entry.source == "discovered"
    reloaded = RouteBindingService(path)
    reloaded.load()
    persisted = reloaded.get_entry("line:demo:C123")
    assert persisted is not None
    assert persisted.chatbot == "buddy"
    assert persisted.profile_name == "default_group_safe"
    cfg = load_route_bindings(path)
    assert "line:demo:C123" in cfg.route_bindings_auto
    assert cfg.route_bindings_manual == {}


def test_route_binding_service_preserves_manual_exact_binding(tmp_path):
    path = tmp_path / "route_bindings.yaml"
    service = RouteBindingService(path)
    service.load()
    service.upsert_entry(
        "line:demo:C123",
        RouteBindingEntry(
            match={"platform": "line:demo", "group_id": "C123"},
            chatbot="manual-bot",
            source="manual",
        ),
    )

    state = RouteOnboardingState(
        route_id="line:demo:C123",
        platform="line:demo",
        conversation_id="C123",
        route_type="group",
        chatbot="discovered-bot",
        reply_policy="never",
        processing_policy="none",
        observation=None,
        label=None,
        profile_name="default_group_safe",
        discovery_type="join",
        discovered_at=datetime(2026, 4, 7, tzinfo=timezone.utc),
    )

    entry = service.upsert_from_onboarding(state)

    assert entry.chatbot == "manual-bot"
    assert entry.source == "manual"
    assert service.config().route_bindings_auto == {}


def test_route_binding_service_migrates_legacy_route_bindings_shape(tmp_path):
    path = tmp_path / "route_bindings.yaml"
    path.write_text(
        """
route_bindings:
  line:demo:C123:
    match:
      platform: line:demo
      group_id: C123
    chatbot: discovered-bot
    source: discovered
  line:demo:U123:
    match:
      platform: line:demo
      user_id: U123
    chatbot: manual-bot
    source: manual
fallback_bindings: []
""".strip(),
        encoding="utf-8",
    )

    cfg = load_route_bindings(path)

    assert "line:demo:C123" in cfg.route_bindings_auto
    assert "line:demo:U123" in cfg.route_bindings_manual


def test_route_binding_service_marks_and_skips_self_write(tmp_path):
    path = tmp_path / "route_bindings.yaml"
    service = RouteBindingService(path)
    service.upsert_manual_entry(
        "line:demo:U123",
        RouteBindingEntry(
            match={"platform": "line:demo", "user_id": "U123"},
            chatbot="buddy",
            source="manual",
        ),
    )
    service.save()

    assert service.should_skip_self_write(path) is True
    path.write_text(path.read_text(encoding="utf-8") + "\n# external edit\n", encoding="utf-8")
    assert service.should_skip_self_write(path) is False
