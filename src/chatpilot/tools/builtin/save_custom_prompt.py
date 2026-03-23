"""save_custom_prompt tool — record user preferences and habits."""

from __future__ import annotations

import logging
from typing import Any, Callable

from copilot.types import ToolInvocation, ToolResult

from chatpilot.core.types import AccessLevel, ToolDefinition

logger = logging.getLogger(__name__)


def create_save_custom_prompt_tool(
    memory_store: Any,
    get_session_fn: Callable[[str], Any],
) -> ToolDefinition:
    """Create a save_custom_prompt tool definition.

    Parameters
    ----------
    memory_store:
        MemoryStore instance for persistence.
    get_session_fn:
        ``Callable[[str], ChatbotSession | None]`` — look up a live session
        by route_id so we can mark ``needs_rebuild=True``.
    """

    async def handler(invocation: ToolInvocation) -> ToolResult:
        args = invocation.get("arguments") or {}
        session_id = invocation.get("session_id", "")
        route_id = session_id.split("__")[0].replace("-", ":", 1)

        text = args.get("text", "").strip()
        if not text:
            return ToolResult(
                textResultForLlm="請提供偏好內容",
                resultType="failure",
            )

        category = args.get("category", "general").strip()
        valid_categories = {"tone", "format", "method", "general"}
        if category not in valid_categories:
            category = "general"

        try:
            prompt_id = await memory_store.save(
                route_id,
                "custom_prompt",
                {"text": text, "category": category},
            )
        except Exception as e:
            logger.error("save_custom_prompt failed: %s", e)
            return ToolResult(
                textResultForLlm=f"儲存失敗: {e}",
                resultType="failure",
            )

        # Mark session for rebuild so new prompt takes effect next turn
        session = get_session_fn(route_id)
        if session is not None:
            session.needs_rebuild = True

        return ToolResult(
            textResultForLlm=(
                f"已記錄偏好（{category}），ID: {prompt_id[:8]}。"
                "下次對話時將自動套用。"
            ),
            resultType="success",
        )

    return ToolDefinition(
        name="save_custom_prompt",
        description=(
            "記錄使用者的偏好和使用習慣。"
            "當使用者提到語氣偏好（正式/輕鬆）、回答格式（簡潔/詳細/列表）、"
            "搜尋方法（優先官方文件）等概要性指引時，"
            "先詢問使用者是否要記下來，同意後呼叫此工具。"
            "記錄後會在下次對話中自動套用。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "偏好或習慣描述",
                },
                "category": {
                    "type": "string",
                    "description": "分類: tone / format / method / general",
                    "enum": ["tone", "format", "method", "general"],
                },
            },
            "required": ["text"],
        },
        handler=handler,
        access_level=AccessLevel.GLOBAL,
    )
