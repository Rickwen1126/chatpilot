"""list_custom_prompts tool — list saved user preferences."""

from __future__ import annotations

import logging
from typing import Any

from copilot.types import ToolInvocation, ToolResult

from chatpilot.core.types import AccessLevel, ToolDefinition
from chatpilot.tools.session_context import get_session_context

logger = logging.getLogger(__name__)


def create_list_custom_prompts_tool(memory_store: Any) -> ToolDefinition:
    """Create a list_custom_prompts tool definition.

    Handler follows SDK ToolHandler signature: (ToolInvocation) -> ToolResult.
    """

    async def handler(invocation: ToolInvocation) -> ToolResult:
        route_id = get_session_context(invocation).route_id

        try:
            prompts = await memory_store.list(route_id, "custom_prompt")
        except Exception as e:
            logger.error("list_custom_prompts failed: %s", e)
            return ToolResult(
                textResultForLlm=f"查詢失敗: {e}",
                resultType="failure",
            )

        if not prompts:
            return ToolResult(
                textResultForLlm="目前沒有儲存任何偏好設定。",
                resultType="success",
            )

        lines: list[str] = []
        for p in prompts:
            category = p.get("category", "general")
            lines.append(f"- [{p['id'][:8]}] ({category}) {p['text']}")

        return ToolResult(
            textResultForLlm=f"共 {len(prompts)} 筆偏好設定:\n" + "\n".join(lines),
            resultType="success",
        )

    return ToolDefinition(
        name="list_custom_prompts",
        description="列出已儲存的偏好設定。",
        parameters={
            "type": "object",
            "properties": {},
        },
        handler=handler,
        access_level=AccessLevel.GLOBAL,
    )
