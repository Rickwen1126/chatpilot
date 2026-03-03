"""Dispatcher — 3-phase message routing logic."""

from __future__ import annotations

from chatpilot.agents.base import BaseAgent
from chatpilot.core.types import (
    DispatchResult,
    FallbackMatch,
    Ignored,
    KeywordMatch,
    Message,
    RouteMap,
    RouteRule,
)

AgentRegistry = dict[str, BaseAgent]


def dispatch(
    message: Message,
    route_map: RouteMap,
    agents: AgentRegistry,
) -> tuple[DispatchResult, BaseAgent | None]:
    """Route a message to an agent using 3-phase lookup.

    Phase 1: Exact (platform, conversation_id) match
    Phase 2: If no exact match, try (platform, None) as private-chat fallback
    Phase 3: Within matched rule — keyword scan, then fallback_agent
    """
    rule = _find_rule(message, route_map)
    if rule is None:
        return Ignored(reason="no_route"), None

    # Keyword substring scan (in order)
    for kw in rule.keywords:
        if kw.keyword in message.text:
            agent = agents.get(kw.agent_name)
            if agent is not None:
                return KeywordMatch(
                    agent_name=kw.agent_name,
                    keyword=kw.keyword,
                    model=rule.model,
                ), agent

    # Fallback agent
    if rule.fallback_agent:
        agent = agents.get(rule.fallback_agent)
        if agent is not None:
            return FallbackMatch(
                agent_name=rule.fallback_agent, model=rule.model
            ), agent

    return Ignored(reason="no_fallback"), None


def _find_rule(message: Message, route_map: RouteMap) -> RouteRule | None:
    """Find matching route rule using 2-phase lookup."""
    # Phase 1: exact (platform, conversation_id) match
    for rule in route_map.routes:
        if (
            rule.platform == message.platform
            and rule.conversation_id == message.conversation_id
        ):
            return rule

    # Phase 2: (platform, None) private-chat fallback
    if message.conversation_id is not None:
        return None  # Group messages don't fall through to private-chat rules

    for rule in route_map.routes:
        if rule.platform == message.platform and rule.conversation_id is None:
            return rule

    return None
