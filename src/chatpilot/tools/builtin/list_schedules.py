"""list_schedules tool — list all reminders and scheduled tasks for the current route."""

from __future__ import annotations

import logging
from typing import Any

from copilot.types import ToolInvocation, ToolResult

from chatpilot.core.types import AccessLevel, ToolDefinition

logger = logging.getLogger(__name__)


def create_list_schedules_tool(memory_store: Any) -> ToolDefinition:
    """Create a list_schedules tool definition.

    Handler follows SDK ToolHandler signature: (ToolInvocation) -> ToolResult.
    """

    async def handler(invocation: ToolInvocation) -> ToolResult:
        session_id = invocation.get("session_id", "")
        route_id = session_id.split("__")[0].replace("-", ":", 1)

        try:
            reminders = await memory_store.list(route_id, "reminder")
            schedules = await memory_store.list(route_id, "schedule")
        except Exception as e:
            logger.error("list_schedules failed: %s", e)
            return ToolResult(
                textResultForLlm=f"查詢失敗: {e}",
                resultType="failure",
            )

        # Filter to pending items only
        reminders = [r for r in reminders if r.get("status", "pending") == "pending"]
        schedules = [s for s in schedules if s.get("status", "pending") == "pending"]

        if not reminders and not schedules:
            return ToolResult(
                textResultForLlm="目前沒有任何排程或提醒。",
                resultType="success",
            )

        lines: list[str] = []
        idx = 1

        for r in reminders:
            due_at = r.get("due_at", "")
            text = r.get("text", "")
            lines.append(f"{idx}. [reminder] {due_at} {text}（ID: {r['id'][:8]}）")
            idx += 1

        for s in schedules:
            cron_expr = s.get("cron_expr", "")
            pipeline_name = s.get("pipeline_name", "")
            input_data = s.get("input_data", "")
            label = f"{pipeline_name} {input_data}".strip()
            lines.append(f"{idx}. [schedule] {cron_expr} {label}（ID: {s['id'][:8]}）")
            idx += 1

        total = len(reminders) + len(schedules)
        return ToolResult(
            textResultForLlm=f"共 {total} 筆排程/提醒:\n" + "\n".join(lines),
            resultType="success",
        )

    return ToolDefinition(
        name="list_schedules",
        description="列出目前所有的提醒和排程任務。",
        parameters={
            "type": "object",
            "properties": {},
        },
        handler=handler,
        access_level=AccessLevel.GLOBAL,
    )
