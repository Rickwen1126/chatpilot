"""ToolFactory — central tool registration and access control."""

from __future__ import annotations

import logging
from typing import Any, Callable

from copilot.types import Tool as SdkTool

from chatpilot.core.types import AccessLevel, ToolDefinition
from chatpilot.tools.registry import ToolRegistry
from chatpilot.tools.session_context import SessionContextRegistry

logger = logging.getLogger(__name__)

ToolHandler = Callable[..., Any]

# Access levels allowed per context
_CHATBOT_LEVELS = (AccessLevel.GLOBAL, AccessLevel.CHATBOT_ONLY, AccessLevel.AGENT_TEAM_TRIGGER)
_PIPELINE_LEVELS = (AccessLevel.GLOBAL, AccessLevel.AGENT_TEAM_ONLY)
_OBSERVER_LEVELS = (AccessLevel.GLOBAL, AccessLevel.OBSERVER_ONLY)


class ToolFactory:
    """Central tool registration and distribution center."""

    def __init__(
        self,
        session_context_registry: SessionContextRegistry | None = None,
    ) -> None:
        self._registry = ToolRegistry()
        self._session_context_registry = (
            session_context_registry or SessionContextRegistry()
        )

    @property
    def session_context_registry(self) -> SessionContextRegistry:
        return self._session_context_registry

    def register(self, definition: ToolDefinition) -> None:
        self._registry.register(definition)

    def get_tools_for_chatbot(self, tool_names: list[str]) -> list[SdkTool]:
        """Get tools available for a chatbot session.

        Allows: GLOBAL, CHATBOT_ONLY, AGENT_TEAM_TRIGGER.
        """
        result: list[SdkTool] = []
        for name in tool_names:
            if not self._registry.has(name):
                logger.warning("Tool '%s' not found, skipping", name)
                continue
            defn = self._registry.get(name)
            if defn.access_level in _CHATBOT_LEVELS:
                result.append(_to_sdk_tool(
                    defn,
                    session_context_registry=self._session_context_registry,
                ))
        return result

    def get_tools_for_pipeline(self, tool_names: list[str]) -> list[SdkTool]:
        """Get tools available for a pipeline agent.

        Allows: GLOBAL, AGENT_TEAM_ONLY.
        Blocks: AGENT_TEAM_TRIGGER (recursion guard, enforced by type).
        """
        result: list[SdkTool] = []
        for name in tool_names:
            if not self._registry.has(name):
                logger.warning("Tool '%s' not found, skipping", name)
                continue
            defn = self._registry.get(name)
            if defn.access_level == AccessLevel.AGENT_TEAM_TRIGGER:
                raise ValueError(
                    f"Tool '{name}' is AGENT_TEAM_TRIGGER "
                    f"and cannot be used inside a pipeline"
                )
            if defn.access_level in _PIPELINE_LEVELS:
                result.append(_to_sdk_tool(
                    defn,
                    session_context_registry=self._session_context_registry,
                ))
        return result

    def get_tools_for_observer(self, tool_names: list[str]) -> list[SdkTool]:
        """Get tools available for an observer worker session.

        Allows: GLOBAL, OBSERVER_ONLY.
        Blocks chatbot and pipeline-specific tools by default.
        """
        result: list[SdkTool] = []
        for name in tool_names:
            if not self._registry.has(name):
                logger.warning("Tool '%s' not found, skipping", name)
                continue
            defn = self._registry.get(name)
            if defn.access_level in _OBSERVER_LEVELS:
                result.append(
                    _to_sdk_tool(
                        defn,
                        session_context_registry=self._session_context_registry,
                    )
                )
        return result

    def get_handler(self, tool_name: str) -> ToolHandler:
        return self._registry.get(tool_name).handler

    def list_tools(self) -> list[ToolDefinition]:
        return self._registry.all()


def _to_sdk_tool(
    defn: ToolDefinition,
    *,
    session_context_registry: SessionContextRegistry | None = None,
) -> SdkTool:
    """Convert internal ToolDefinition to SDK Tool dataclass."""
    original = defn.handler

    async def _logged_handler(invocation: Any) -> Any:
        enriched_invocation = dict(invocation)
        args = enriched_invocation.get("arguments") or {}
        session_id = enriched_invocation.get("session_id", "")
        context = None
        if session_context_registry is not None and "session_context" not in enriched_invocation:
            context = session_context_registry.resolve(session_id)
            if context is not None:
                enriched_invocation["session_context"] = context.model_dump()
        elif session_context_registry is not None:
            context = session_context_registry.resolve(session_id)
        target_route_id = args.get("route_id", "") if isinstance(args, dict) else ""
        if not isinstance(target_route_id, str):
            target_route_id = ""
        route_id = context.route_id if context is not None else ""
        chatbot_name = context.chatbot_name if context is not None else ""
        logger.info(
            "[tool_call] tool=%s route_id=%s target_route_id=%s "
            "sdk_session_id=%s chatbot=%s args=%s",
            defn.name,
            route_id,
            target_route_id,
            session_id,
            chatbot_name,
            args,
        )
        result = await original(enriched_invocation)
        status = result.get("resultType", "?") if isinstance(result, dict) else "?"
        text = result.get("textResultForLlm", "") if isinstance(result, dict) else ""
        logger.info(
            "[tool_result] tool=%s route_id=%s target_route_id=%s "
            "sdk_session_id=%s chatbot=%s status=%s result=%s",
            defn.name,
            route_id,
            target_route_id,
            session_id,
            chatbot_name,
            status,
            text[:200] if text else "",
        )
        return result

    return SdkTool(
        name=defn.name,
        description=defn.description,
        handler=_logged_handler,
        parameters=defn.parameters,
    )
