"""cancel_schedule tool — cancel a reminder or schedule by index number."""

from __future__ import annotations

import logging
from typing import Any

from copilot.types import ToolInvocation, ToolResult

from chatpilot.core.types import AccessLevel, ToolDefinition

logger = logging.getLogger(__name__)


def create_cancel_schedule_tool(memory_store: Any) -> ToolDefinition:
    """Create a cancel_schedule tool that cancels by index from list."""

    async def handler(invocation: ToolInvocation) -> ToolResult:
        args = invocation.get("arguments") or {}
        session_id = invocation.get("session_id", "")
        route_id = session_id.split("__")[0].replace("-", ":", 1)

        index = args.get("index", 0)
        try:
            index = int(index)
        except (TypeError, ValueError):
            return ToolResult(
                textResultForLlm="請提供要取消的編號（數字）",
                resultType="failure",
            )

        if index < 1:
            return ToolResult(
                textResultForLlm="編號必須大於 0",
                resultType="failure",
            )

        # Rebuild the same list as list_schedules
        items: list[tuple[str, str, dict]] = []
        try:
            reminders = await memory_store.list(route_id, "reminder")
            for r in reminders:
                if r.get("status", "pending") == "pending":
                    items.append(("reminder", r["id"], r))
            schedules = await memory_store.list(route_id, "schedule")
            for s in schedules:
                if s.get("status", "pending") == "pending":
                    items.append(("schedule", s["id"], s))
        except Exception as e:
            return ToolResult(
                textResultForLlm=f"查詢失敗: {e}",
                resultType="failure",
            )

        if index > len(items):
            return ToolResult(
                textResultForLlm=f"只有 {len(items)} 筆排程，沒有第 {index} 筆",
                resultType="failure",
            )

        type_name, item_id, item = items[index - 1]
        desc = item.get("text", item.get("cron_expr", ""))

        try:
            await memory_store.delete(route_id, type_name, item_id)
        except Exception as e:
            return ToolResult(
                textResultForLlm=f"取消失敗: {e}",
                resultType="failure",
            )

        return ToolResult(
            textResultForLlm=f"已取消第 {index} 筆 [{type_name}]：{desc}",
            resultType="success",
        )

    return ToolDefinition(
        name="cancel_schedule",
        description=(
            "取消一筆提醒或排程。使用 list_schedules 列出的編號，"
            "例如使用者說「取消第 2 個」就傳 index=2。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "index": {
                    "type": "integer",
                    "description": "要取消的項目編號（從 list_schedules 取得）",
                },
            },
            "required": ["index"],
        },
        handler=handler,
        access_level=AccessLevel.GLOBAL,
    )
