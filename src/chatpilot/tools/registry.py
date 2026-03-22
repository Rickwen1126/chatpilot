"""Tool registry — stores tool definitions."""

from __future__ import annotations

import logging

from chatpilot.core.types import ToolDefinition

logger = logging.getLogger(__name__)


class ToolRegistry:
    """In-memory tool definition storage."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, definition: ToolDefinition) -> None:
        if definition.name in self._tools:
            raise ValueError(f"Tool '{definition.name}' already registered")
        self._tools[definition.name] = definition
        logger.info(
            "Registered tool: %s (access=%s)", definition.name, definition.access_level.name
        )

    def get(self, name: str) -> ToolDefinition:
        if name not in self._tools:
            raise KeyError(f"Tool '{name}' not found")
        return self._tools[name]

    def has(self, name: str) -> bool:
        return name in self._tools

    def all(self) -> list[ToolDefinition]:
        return list(self._tools.values())
