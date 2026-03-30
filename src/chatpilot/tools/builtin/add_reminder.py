from __future__ import annotations

from copilot.types import ToolInvocation, ToolResult

from chatpilot.core.types import AccessLevel, ToolDefinition
from chatpilot.tools.session_context import get_session_context


def create_add_reminder_tool(memory_store) -> ToolDefinition:
    async def handler(invocation: ToolInvocation) -> ToolResult:
        args = invocation.get("arguments") or {}
        route_id = get_session_context(invocation).route_id

        text = args.get("text", "")
        due_at = args.get("due_at", "")

        if not text or not due_at:
            return ToolResult(textResultForLlm="需要提供提醒內容和時間", resultType="failure")

        id = await memory_store.save(route_id, "reminder", {
            "text": text,
            "due_at": due_at,  # LLM should provide ISO 8601 UTC
        })
        return ToolResult(
            textResultForLlm=f"已設定提醒：{due_at} {text}（ID: {id[:8]}）",
            resultType="success",
        )

    return ToolDefinition(
        name="add_reminder",
        description=(
            "設定一次性提醒。提供提醒內容和到期時間（UTC ISO 8601 格式），"
            "系統會在到期時主動推送通知。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "提醒內容"},
                "due_at": {
                    "type": "string",
                    "description": "到期時間（UTC ISO 8601）",
                },
            },
            "required": ["text", "due_at"],
        },
        handler=handler,
        access_level=AccessLevel.GLOBAL,
    )
