"""Runtime route onboarding state and discovery rule matching."""

from __future__ import annotations

from dataclasses import dataclass

from chatpilot.core.config import GatewayConfig
from chatpilot.core.types import (
    DiscoveryEvent,
    DiscoveryProfileConfig,
    DiscoveryRuleConfig,
    RouteOnboardingState,
)


@dataclass(frozen=True)
class _MatchedDiscoveryRule:
    rank: int
    profile_name: str


def _keyword_match(label: str | None, keywords: list[str]) -> bool:
    if not label or not keywords:
        return False
    lower = label.casefold()
    return any(keyword.casefold() in lower for keyword in keywords)


def _rule_rank(
    rule: DiscoveryRuleConfig,
    event: DiscoveryEvent,
    label: str | None,
) -> int | None:
    if rule.route_type != event.route_type:
        return None
    if rule.platform and rule.platform != event.platform:
        return None

    if rule.route_type == "group" and rule.group_id:
        return 4 if rule.group_id == event.conversation_id else None
    if rule.route_type == "user" and rule.user_id:
        return 4 if rule.user_id == event.conversation_id else None
    if rule.label_keywords:
        return 3 if _keyword_match(label, rule.label_keywords) else None
    if rule.platform:
        return 2
    return 1


def select_discovery_profile(
    config: GatewayConfig,
    event: DiscoveryEvent,
    *,
    label: str | None = None,
) -> tuple[str, DiscoveryProfileConfig] | None:
    best: _MatchedDiscoveryRule | None = None
    for rule in config.discovery_rules:
        rank = _rule_rank(rule, event, label)
        if rank is None:
            continue
        if best is None or rank > best.rank:
            best = _MatchedDiscoveryRule(rank=rank, profile_name=rule.profile)

    if best is None:
        return None
    return best.profile_name, config.discovery_profiles[best.profile_name]


def materialize_onboarding_state(
    config: GatewayConfig,
    event: DiscoveryEvent,
    *,
    label: str | None = None,
) -> RouteOnboardingState | None:
    matched = select_discovery_profile(config, event, label=label)
    if matched is None:
        return None

    profile_name, profile = matched
    return RouteOnboardingState(
        route_id=event.route_id,
        platform=event.platform,
        conversation_id=event.conversation_id,
        route_type=event.route_type,
        chatbot=profile.chatbot,
        reply_policy=profile.reply_policy,
        processing_policy=profile.processing_policy,
        observation=profile.observation,
        label=label,
        profile_name=profile_name,
        discovery_type=event.discovery_type,
        discovered_at=event.timestamp,
    )


class RouteOnboardingRegistry:
    """In-memory registry of materialized route onboarding states."""

    def __init__(self) -> None:
        self._states: dict[str, RouteOnboardingState] = {}

    def register(self, state: RouteOnboardingState) -> None:
        self._states[state.route_id] = state

    def resolve(self, route_id: str) -> RouteOnboardingState | None:
        return self._states.get(route_id)

    def list_states(self) -> list[RouteOnboardingState]:
        return list(self._states.values())

    def clear(self) -> None:
        self._states.clear()
