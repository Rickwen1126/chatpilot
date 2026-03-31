"""ChannelAdapter Protocol — interface for all channel adapters."""

from __future__ import annotations

from typing import Any, Mapping, Protocol, runtime_checkable

from fastapi import Request

from chatpilot.core.types import Message, Response
from chatpilot.files.models import SourceFetchResult, SourceHandleInput


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

    def build_source_handle(
        self,
        *,
        route_id: str,
        kind: str,
        native_locator: str,
        filename: str | None = None,
        mime_type: str | None = None,
        platform_context: Mapping[str, Any] | None = None,
    ) -> SourceHandleInput:
        """Translate platform-specific source identity into SourceHandleInput."""
        ...

    @property
    def format_hint(self) -> str | None:
        """Platform-specific formatting instructions for the LLM.

        Returned string is injected into the prompt so the chatbot
        respects the platform's display limitations.
        New adapters MUST define this if the platform has formatting constraints.
        Return None if the platform supports Markdown.
        """
        ...

    async def download_media(self, media_id: str) -> bytes | None:
        """Download media content by platform-specific ID.

        Returns raw bytes, or None if not supported / not found.
        Used by download_media tool when LLM decides to view an image.
        """
        ...

    async def fetch_source_file(
        self,
        source: SourceHandleInput,
    ) -> SourceFetchResult | None:
        """Fetch a canonical source handle back into bytes + metadata."""
        ...
