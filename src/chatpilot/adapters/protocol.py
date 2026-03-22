"""ChannelAdapter Protocol — interface for all channel adapters."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from fastapi import Request

from chatpilot.core.types import Message, Response


@runtime_checkable
class ChannelAdapter(Protocol):
    """Channel adapter interface. Each platform implements this Protocol."""

    @property
    def platform(self) -> str:
        """Platform identifier (e.g. "line", "mock")."""
        ...

    async def verify_request(self, request: Request) -> bool:
        """Verify webhook request signature.

        Returns True if valid. Raises AdapterError if invalid.
        """
        ...

    async def parse_messages(self, request: Request) -> list[Message]:
        """Parse webhook request into unified Message format."""
        ...

    async def send_reply(self, message: Message, response: Response) -> None:
        """Reply to an inbound message (uses reply token etc)."""
        ...

    async def push_message(self, route_id: str, response: Response) -> None:
        """Push a message to a conversation (for async task results)."""
        ...
