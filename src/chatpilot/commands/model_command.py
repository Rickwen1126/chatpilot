"""/model command — query or switch the Copilot model for a route."""

from __future__ import annotations

import logging

from chatpilot.core.types import RouteMap, RouteRule

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gpt-4.1"

MODEL_ALIASES: dict[str, str] = {
    # Exact IDs
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
    # Short aliases
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

# Deduplicated list for display
AVAILABLE_MODELS = sorted(set(MODEL_ALIASES.values()))


def fuzzy_match(user_input: str) -> str | None:
    """Match user input to a model ID. Returns canonical model name or None."""
    normalized = user_input.lower().strip()
    if not normalized:
        return None

    # Exact alias lookup
    if normalized in MODEL_ALIASES:
        return MODEL_ALIASES[normalized]

    # Substring search across canonical model IDs
    for model_id in AVAILABLE_MODELS:
        if normalized in model_id:
            return model_id

    return None


def handle_model_command(
    text: str,
    route_rule: RouteRule | None,
    route_map: RouteMap,
    routes_path: str,
) -> str:
    """Handle /model command. Returns reply text.

    /model         → show current model
    /model <name>  → fuzzy match and switch model
    """
    from chatpilot.dispatch.route_loader import save_routes

    parts = text.strip().split(maxsplit=1)
    current_model = (route_rule.model if route_rule else None) or DEFAULT_MODEL

    # /model (no argument) → show current
    if len(parts) == 1:
        return f"目前使用的模型：{current_model}"

    # /model <name> → switch
    user_input = parts[1]
    matched = fuzzy_match(user_input)

    if matched is None:
        available = ", ".join(AVAILABLE_MODELS)
        return f'找不到匹配的模型「{user_input}」\n可用：{available}'

    if route_rule is None:
        return "找不到對應的路由規則，無法切換模型。"

    route_rule.model = matched
    save_routes(routes_path, route_map)
    logger.info("Model switched to %s for route %s", matched, route_rule.platform)
    return f"模型已切換為：{matched} ✓"
