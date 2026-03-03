"""Warehouse agent stub — for routing validation only."""

from __future__ import annotations

from chatpilot.core.types import Message, Response


class WarehouseAgent:
    """Stub agent for multi-agent routing validation."""

    @property
    def name(self) -> str:
        return "warehouse-agent"

    async def handle(
        self, message: Message, session_id: str, model: str | None = None
    ) -> Response:
        return Response(text=f"[warehouse-agent] 收到: {message.text}")


warehouse_agent = WarehouseAgent()
