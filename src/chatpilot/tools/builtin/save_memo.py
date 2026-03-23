"""save_memo tool — persist important information as long-term memory."""

from __future__ import annotations

import logging
from typing import Any

from copilot.types import ToolInvocation, ToolResult

from chatpilot.core.types import AccessLevel, ToolDefinition

logger = logging.getLogger(__name__)


def create_save_memo_tool(memory_store: Any) -> ToolDefinition:
    """Create a save_memo tool definition.

    Handler follows SDK ToolHandler signature: (ToolInvocation) -> ToolResult.
    """

    async def handler(invocation: ToolInvocation) -> ToolResult:
        args = invocation.get("arguments") or {}
        session_id = invocation.get("session_id", "")
        route_id = session_id.split("@")[0].replace("-", ":", 1)

        text = args.get("text", "").strip()
        if not text:
            return ToolResult(
                textResultForLlm="請提供要記住的內容",
                resultType="failure",
            )

        tags_raw = args.get("tags", "")
        tags = [t.strip() for t in tags_raw.split(",") if t.strip()] if tags_raw else []

        try:
            memo_id = await memory_store.save(
                route_id,
                "memo",
                {"text": text, "tags": tags},
            )
            tag_info = f"（標籤: {', '.join(tags)}）" if tags else ""
            return ToolResult(
                textResultForLlm=f"已記住{tag_info}，ID: {memo_id[:8]}",
                resultType="success",
            )
        except Exception as e:
            logger.error("save_memo failed: %s", e)
            return ToolResult(
                textResultForLlm=f"儲存失敗: {e}",
                resultType="failure",
            )

    return ToolDefinition(
        name="save_memo",
        description=(
            "儲存重要資訊作為長期記憶。"
            "當對話中出現約定、偏好、關鍵數據或統整結論時，"
            "先詢問使用者是否需要記下來，同意後再呼叫此工具。"
            "使用者也可以直接說「記住 XXX」觸發。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "要記住的內容",
                },
                "tags": {
                    "type": "string",
                    "description": "標籤，以逗號分隔（選填）",
                },
            },
            "required": ["text"],
        },
        handler=handler,
        access_level=AccessLevel.GLOBAL,
    )
