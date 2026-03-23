"""cancel_schedule tool — cancel a reminder or scheduled task by its ID."""

from __future__ import annotations

import logging
from typing import Any

from copilot.types import ToolInvocation, ToolResult

from chatpilot.core.types import AccessLevel, ToolDefinition

logger = logging.getLogger(__name__)


def create_cancel_schedule_tool(memory_store: Any) -> ToolDefinition:
    """Create a cancel_schedule tool definition.

    Handler follows SDK ToolHandler signature: (ToolInvocation) -> ToolResult.
    """

    async def handler(invocation: ToolInvocation) -> ToolResult:
        args = invocation.get("arguments") or {}
        session_id = invocation.get("session_id", "")
        route_id = session_id.replace("-", ":", 1)

        item_id = args.get("item_id", "").strip()
        if not item_id:
            return ToolResult(
                textResultForLlm="請提供要取消的排程/提醒 ID",
                resultType="failure",
            )

        try:
            deleted = await memory_store.delete(route_id, "reminder", item_id)
            if not deleted:
                deleted = await memory_store.delete(route_id, "schedule", item_id)
        except Exception as e:
            logger.error("cancel_schedule failed: %s", e)
            return ToolResult(
                textResultForLlm=f"取消失敗: {e}",
                resultType="failure",
            )

        if deleted:
            return ToolResult(
                textResultForLlm=f"已取消排程/提醒 {item_id[:8]}",
                resultType="success",
            )
        return ToolResult(
            textResultForLlm=f"找不到 ID 為 {item_id[:8]} 的排程或提醒",
            resultType="failure",
        )

    return ToolDefinition(
        name="cancel_schedule",
        description="取消一筆提醒或排程任務。",
        parameters={
            "type": "object",
            "properties": {
                "item_id": {
                    "type": "string",
                    "description": "要取消的排程或提醒 ID",
                },
            },
            "required": ["item_id"],
        },
        handler=handler,
        access_level=AccessLevel.GLOBAL,
    )
