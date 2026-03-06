"""CommandHandler — instant slash commands (/model, /agent)."""

from __future__ import annotations

import logging

from chatpilot.core.types import ConversationRoute, Message, RouteConfig
from chatpilot.dispatch.route_loader import save_route_config

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gpt-4.1"

MODEL_ALIASES: dict[str, str] = {
    "gpt-4.1": "gpt-4.1",
    "gpt-5-mini": "gpt-5-mini",
    "gpt-5.1": "gpt-5.1",
    "gpt-5.2": "gpt-5.2",
    "claude-haiku-4.5": "claude-haiku-4.5",
    "claude-sonnet-4": "claude-sonnet-4",
    "claude-sonnet-4.5": "claude-sonnet-4.5",
    "claude-sonnet-4.6": "claude-sonnet-4.6",
    "claude-opus-4.5": "claude-opus-4.5",
    "claude-opus-4.6": "claude-opus-4.6",
    "gemini-3-pro-preview": "gemini-3-pro-preview",
    "4.1": "gpt-4.1",
    "5mini": "gpt-5-mini",
    "5.1": "gpt-5.1",
    "5.2": "gpt-5.2",
    "haiku": "claude-haiku-4.5",
    "sonnet": "claude-sonnet-4.6",
    "sonnet4": "claude-sonnet-4",
    "sonnet4.5": "claude-sonnet-4.5",
    "sonnet4.6": "claude-sonnet-4.6",
    "opus": "claude-opus-4.6",
    "opus4.5": "claude-opus-4.5",
    "opus4.6": "claude-opus-4.6",
    "gemini": "gemini-3-pro-preview",
}

AVAILABLE_MODELS = sorted(set(MODEL_ALIASES.values()))


def _fuzzy_match_model(user_input: str) -> str | None:
    normalized = user_input.lower().strip()
    if not normalized:
        return None
    if normalized in MODEL_ALIASES:
        return MODEL_ALIASES[normalized]
    for model_id in AVAILABLE_MODELS:
        if normalized in model_id:
            return model_id
    return None


class CommandHandler:
    """Handles instant slash commands. Bypasses session gate."""

    def try_handle(
        self,
        msg: Message,
        route_config: RouteConfig,
        routes_path: str,
    ) -> str | None:
        """Returns reply text if msg is a command, None otherwise."""
        text = msg.text.strip()
        if text.lower().startswith("/model"):
            return self._handle_model(text, msg, route_config, routes_path)
        if text.lower().startswith("/agent"):
            return self._handle_agent(text, msg, route_config, routes_path)
        return None

    def _get_conversation_key(self, msg: Message) -> str:
        return msg.conversation_id or "null"

    def _get_route(
        self, msg: Message, route_config: RouteConfig
    ) -> ConversationRoute | None:
        platform_config = route_config.platforms.get(msg.platform)
        if not platform_config:
            return None
        key = self._get_conversation_key(msg)
        return platform_config.conversation_routes.get(key)

    def _ensure_route(
        self, msg: Message, route_config: RouteConfig
    ) -> ConversationRoute:
        """Get or create a ConversationRoute for this conversation."""
        platform_config = route_config.platforms.get(msg.platform)
        if not platform_config:
            return ConversationRoute(agent="general-agent")
        key = self._get_conversation_key(msg)
        route = platform_config.conversation_routes.get(key)
        if route is None:
            route = ConversationRoute(agent=platform_config.default_agent)
            platform_config.conversation_routes[key] = route
        return route

    def _handle_agent(
        self,
        text: str,
        msg: Message,
        route_config: RouteConfig,
        routes_path: str,
    ) -> str:
        parts = text.strip().split(maxsplit=1)
        route = self._get_route(msg, route_config)
        current_agent = route.agent if route else "unknown"

        if len(parts) == 1:
            available = ", ".join(route_config.agent_list)
            return f"目前 Agent：{current_agent}\n可用：{available}"

        requested = parts[1].strip().lower()

        # Fuzzy match against agent_list
        matched = None
        for name in route_config.agent_list:
            if requested == name or requested in name:
                matched = name
                break

        if matched is None:
            available = ", ".join(route_config.agent_list)
            return f"找不到 Agent「{parts[1].strip()}」\n可用：{available}"

        route = self._ensure_route(msg, route_config)
        route.agent = matched
        if routes_path:
            save_route_config(routes_path, route_config)
        logger.info(
            "Agent switched to %s for %s/%s",
            matched,
            msg.platform,
            msg.conversation_id,
        )
        return f"Agent 已切換為：{matched} ✓"

    def _handle_model(
        self,
        text: str,
        msg: Message,
        route_config: RouteConfig,
        routes_path: str,
    ) -> str:
        parts = text.strip().split(maxsplit=1)
        route = self._get_route(msg, route_config)
        current_model = (route.model if route else None) or DEFAULT_MODEL

        if len(parts) == 1:
            return f"目前使用的模型：{current_model}"

        matched = _fuzzy_match_model(parts[1])
        if matched is None:
            available = ", ".join(AVAILABLE_MODELS)
            return f"找不到匹配的模型「{parts[1]}」\n可用：{available}"

        route = self._ensure_route(msg, route_config)
        route.model = matched
        if routes_path:
            save_route_config(routes_path, route_config)
        logger.info(
            "Model switched to %s for %s/%s",
            matched,
            msg.platform,
            msg.conversation_id,
        )
        return f"模型已切換為：{matched} ✓"
