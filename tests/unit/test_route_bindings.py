from __future__ import annotations

from datetime import datetime, timezone

from chatpilot.core.route_bindings import RouteBindingEntry, RouteBindingService
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
