"""delete_custom_prompt tool — remove a custom prompt by its id."""

from __future__ import annotations

import logging
from typing import Any, Callable

from copilot.types import ToolInvocation, ToolResult

from chatpilot.core.types import AccessLevel, ToolDefinition

logger = logging.getLogger(__name__)


def create_delete_custom_prompt_tool(
    memory_store: Any,
    get_session_fn: Callable[[str], Any],
) -> ToolDefinition:
    """Create a delete_custom_prompt tool definition.

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
        route_id = session_id.split("@")[0].replace("-", ":", 1)

        prompt_id = args.get("prompt_id", "").strip()
        if not prompt_id:
            return ToolResult(
                textResultForLlm="請提供要刪除的偏好設定 ID",
                resultType="failure",
            )

        try:
            deleted = await memory_store.delete(route_id, "custom_prompt", prompt_id)
        except Exception as e:
            logger.error("delete_custom_prompt failed: %s", e)
            return ToolResult(
                textResultForLlm=f"刪除失敗: {e}",
                resultType="failure",
            )

        if not deleted:
            return ToolResult(
                textResultForLlm=f"找不到 ID 為 {prompt_id[:8]} 的偏好設定",
                resultType="failure",
            )

        # Mark session for rebuild so removed prompt no longer applies
        session = get_session_fn(route_id)
        if session is not None:
            session.needs_rebuild = True

        return ToolResult(
            textResultForLlm=f"已刪除偏好設定 {prompt_id[:8]}，下次對話將不再套用。",
            resultType="success",
        )

    return ToolDefinition(
        name="delete_custom_prompt",
        description="刪除一筆已儲存的偏好設定。",
        parameters={
            "type": "object",
            "properties": {
                "prompt_id": {
                    "type": "string",
                    "description": "要刪除的偏好設定 ID",
                },
            },
            "required": ["prompt_id"],
        },
        handler=handler,
        access_level=AccessLevel.GLOBAL,
    )
