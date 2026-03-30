"""list_memos tool — list all saved memos for the current route."""

from __future__ import annotations

import logging
from typing import Any

from copilot.types import ToolInvocation, ToolResult

from chatpilot.core.types import AccessLevel, ToolDefinition
from chatpilot.tools.session_context import get_session_context

logger = logging.getLogger(__name__)


def create_list_memos_tool(memory_store: Any) -> ToolDefinition:
    """Create a list_memos tool definition.

    Handler follows SDK ToolHandler signature: (ToolInvocation) -> ToolResult.
    """

    async def handler(invocation: ToolInvocation) -> ToolResult:
        route_id = get_session_context(invocation).route_id

        try:
            memos = await memory_store.list(route_id, "memo")
        except Exception as e:
            logger.error("list_memos failed: %s", e)
            return ToolResult(
                textResultForLlm=f"查詢失敗: {e}",
                resultType="failure",
            )

        if not memos:
            return ToolResult(
                textResultForLlm="目前沒有儲存任何記憶。",
                resultType="success",
            )

        lines: list[str] = []
        for m in memos:
            tags = m.get("tags", [])
            tag_str = f" [{', '.join(tags)}]" if tags else ""
            lines.append(f"- [{m['id']}]{tag_str} {m['text']}")

        return ToolResult(
            textResultForLlm=f"共 {len(memos)} 筆記憶:\n" + "\n".join(lines),
            resultType="success",
        )

    return ToolDefinition(
        name="list_memos",
        description="列出已儲存的記憶。",
        parameters={
            "type": "object",
            "properties": {},
        },
        handler=handler,
        access_level=AccessLevel.GLOBAL,
    )
