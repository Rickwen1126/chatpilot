"""BaseAgent Protocol — interface for all agents."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from chatpilot.core.types import Message, Response


@runtime_checkable
class BaseAgent(Protocol):
    @property
    def name(self) -> str: ...

    async def handle(
        self, message: Message, session_id: str, model: str | None = None
    ) -> Response: ...


AgentRegistry = dict[str, BaseAgent]
