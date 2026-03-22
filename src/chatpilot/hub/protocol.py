"""MessageHub Protocol — central message processing interface."""

from __future__ import annotations

from typing import Literal, Protocol

from chatpilot.adapters.protocol import ChannelAdapter
from chatpilot.core.types import Message, Response


class MessageHub(Protocol):
    """Central message processing hub. All messages flow through here."""

    async def receive(self, message: Message, adapter: ChannelAdapter) -> None: ...

    async def send_reply(
        self, message: Message, response: Response, adapter: ChannelAdapter
    ) -> None: ...

    async def push(self, route_id: str, response: Response) -> None: ...

    def get_status(self, route_id: str) -> Literal["idle", "busy"]: ...

    def set_busy(self, route_id: str) -> None: ...

    def set_idle(self, route_id: str) -> None: ...
