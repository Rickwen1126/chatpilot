"""ChannelAdapter Protocol — interface for all channel adapters."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from chatpilot.core.types import Message, Response


@runtime_checkable
class ChannelAdapter(Protocol):
    @property
    def platform(self) -> str: ...

    def verify_signature(self, raw_body: bytes, signature: str) -> bool: ...

    def parse_messages(self, raw_body: bytes) -> list[Message]: ...

    async def send_response(self, message: Message, response: Response) -> None: ...

    async def send_processing_ack(self, message: Message) -> None: ...


AdapterRegistry = dict[str, ChannelAdapter]
