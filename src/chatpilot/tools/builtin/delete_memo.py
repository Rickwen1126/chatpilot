"""delete_memo tool — remove a memo by its id."""

from __future__ import annotations

import logging
from typing import Any

from copilot.types import ToolInvocation, ToolResult

from chatpilot.core.types import AccessLevel, ToolDefinition

logger = logging.getLogger(__name__)


def create_delete_memo_tool(memory_store: Any) -> ToolDefinition:
    """Create a delete_memo tool definition.

    Handler follows SDK ToolHandler signature: (ToolInvocation) -> ToolResult.
    """

    async def handler(invocation: ToolInvocation) -> ToolResult:
        args = invocation.get("arguments") or {}
        session_id = invocation.get("session_id", "")
        route_id = session_id.replace("-", ":", 1)

        memo_id = args.get("memo_id", "").strip()
        if not memo_id:
            return ToolResult(
                textResultForLlm="請提供要刪除的記憶 ID",
                resultType="failure",
            )

        try:
            deleted = await memory_store.delete(route_id, "memo", memo_id)
        except Exception as e:
            logger.error("delete_memo failed: %s", e)
            return ToolResult(
                textResultForLlm=f"刪除失敗: {e}",
                resultType="failure",
            )

        if deleted:
            return ToolResult(
                textResultForLlm=f"已刪除記憶 {memo_id[:8]}",
                resultType="success",
            )
        return ToolResult(
            textResultForLlm=f"找不到 ID 為 {memo_id[:8]} 的記憶",
            resultType="failure",
        )

    return ToolDefinition(
        name="delete_memo",
        description="刪除一筆已儲存的記憶。",
        parameters={
            "type": "object",
            "properties": {
                "memo_id": {
                    "type": "string",
                    "description": "要刪除的記憶 ID",
                },
            },
            "required": ["memo_id"],
        },
        handler=handler,
        access_level=AccessLevel.GLOBAL,
    )
