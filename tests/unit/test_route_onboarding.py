from __future__ import annotations

from datetime import datetime, timezone

from chatpilot.core.config import GatewayConfig
from chatpilot.core.types import DiscoveryEvent, ObservationConfig, RouteOnboardingState
from chatpilot.routing.onboarding import (
    RouteOnboardingRegistry,
    materialize_onboarding_state,
    select_discovery_profile,
)


def _config() -> GatewayConfig:
    return GatewayConfig(
        route_groups={"ops": {"description": "ops"}},
        observation_profiles={
            "warehouse_ops": {
                "mode": "batch",
                "batch_size": 10,
                "instructions": "capture ops",
            }
        },
        discovery_profiles={
            "exact_group": {
                "chatbot": "observer",
                "reply_policy": "never",
                "processing_policy": "none",
            },
            "keyword_group": {
                "chatbot": "observer",
                "reply_policy": "never",
                "processing_policy": "none",
                "observation": {
                    "capture": {"group": "ops", "profile": "warehouse_ops"}
                },
            },
            "channel_group": {
                "chatbot": "buddy",
                "reply_policy": "never",
                "processing_policy": "none",
            },
            "global_group": {
                "chatbot": "buddy",
                "reply_policy": "never",
                "processing_policy": "none",
            },
        },
        discovery_rules=[
            {
                "platform": "line:shinyipaint",
                "route_type": "group",
                "group_id": "C-EXACT",
                "profile": "exact_group",
            },
            {
                "platform": "line:shinyipaint",
                "route_type": "group",
                "label_keywords": ["信益", "倉庫"],
                "profile": "keyword_group",
            },
            {
                "platform": "line:shinyipaint",
                "route_type": "group",
                "profile": "channel_group",
            },
            {
                "route_type": "group",
                "profile": "global_group",
            },
        ],
        chatbots={
            "observer": {"name": "observer", "model": "gpt-5.4-mini", "system_message": "test"},
            "buddy": {"name": "buddy", "model": "gpt-5.4-mini", "system_message": "test"},
        },
    )


def _event(conversation_id: str) -> DiscoveryEvent:
    return DiscoveryEvent(
        discovery_type="join",
        route_type="group",
        platform="line:shinyipaint",
        conversation_id=conversation_id,
        timestamp=datetime(2026, 4, 7, tzinfo=timezone.utc),
    )


def test_select_discovery_profile_uses_exact_before_keyword_and_defaults() -> None:
    matched = select_discovery_profile(_config(), _event("C-EXACT"), label="信益大群組")

    assert matched is not None
    profile_name, profile = matched
    assert profile_name == "exact_group"
    assert profile.chatbot == "observer"


def test_select_discovery_profile_uses_keyword_before_channel_default() -> None:
    matched = select_discovery_profile(_config(), _event("C-OTHER"), label="信益大群組")

    assert matched is not None
    profile_name, profile = matched
    assert profile_name == "keyword_group"
    assert profile.observation is not None


def test_materialize_onboarding_state_uses_channel_default_without_keyword() -> None:
    state = materialize_onboarding_state(_config(), _event("C-OTHER"), label="閒聊群組")

    assert state is not None
    assert state.profile_name == "channel_group"
    assert state.chatbot == "buddy"
    assert state.route_id == "line:shinyipaint:C-OTHER"


def test_route_onboarding_registry_round_trip() -> None:
    registry = RouteOnboardingRegistry()
    state = RouteOnboardingState(
        route_id="line:shinyipaint:C123",
        platform="line:shinyipaint",
        conversation_id="C123",
        route_type="group",
        chatbot="observer",
        reply_policy="never",
        processing_policy="none",
        observation=ObservationConfig.model_validate({}),
        label="測試群組",
        profile_name="default_group",
        discovery_type="join",
        discovered_at=datetime(2026, 4, 7, tzinfo=timezone.utc),
    )

    registry.register(state)

    assert registry.resolve("line:shinyipaint:C123") == state
    assert registry.list_states() == [state]
