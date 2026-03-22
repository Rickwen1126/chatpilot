"""ToolFactory — central tool registration and access control."""

from __future__ import annotations

import logging
from typing import Any, Callable

from copilot.types import Tool as SdkTool

from chatpilot.core.types import AccessLevel, ToolDefinition
from chatpilot.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

ToolHandler = Callable[..., Any]

# Access levels allowed per context
_CHATBOT_LEVELS = (AccessLevel.GLOBAL, AccessLevel.CHATBOT_ONLY, AccessLevel.AGENT_TEAM_TRIGGER)
_PIPELINE_LEVELS = (AccessLevel.GLOBAL, AccessLevel.AGENT_TEAM_ONLY)


class ToolFactory:
    """Central tool registration and distribution center."""

    def __init__(self) -> None:
        self._registry = ToolRegistry()

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
                result.append(_to_sdk_tool(defn))
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
                result.append(_to_sdk_tool(defn))
        return result

    def get_handler(self, tool_name: str) -> ToolHandler:
        return self._registry.get(tool_name).handler

    def list_tools(self) -> list[ToolDefinition]:
        return self._registry.all()


def _to_sdk_tool(defn: ToolDefinition) -> SdkTool:
    """Convert internal ToolDefinition to SDK Tool dataclass."""
    return SdkTool(
        name=defn.name,
        description=defn.description,
        handler=defn.handler,
        parameters=defn.parameters,
    )
