"""schedule_task_cron tool — create a recurring scheduled task via cron expression."""

from __future__ import annotations

import logging
from typing import Any

from copilot.types import ToolInvocation, ToolResult

from chatpilot.core.types import AccessLevel, ToolDefinition

logger = logging.getLogger(__name__)


def create_schedule_task_cron_tool(
    memory_store: Any,
    get_available_tools: Any = None,
) -> ToolDefinition:
    """Create a schedule_task_cron tool definition.

    Handler follows SDK ToolHandler signature: (ToolInvocation) -> ToolResult.
    get_available_tools: callable returning list[str] of registered tool names.
    """

    def _build_description() -> str:
        tools = get_available_tools() if get_available_tools else []
        if tools:
            tools_list = "、".join(f"'{t}'" for t in tools)
            return (
                "建立週期性排程任務。提供 cron 表達式（如 'daily 08:00'、"
                "'weekly mon 09:00'、'interval 30m'）和 tool 名稱。"
                f"可用的 tool：{tools_list}。"
                "只能使用這些已註冊的 tool 名稱，不可自創。"
            )
        return (
            "建立週期性排程任務。提供 cron 表達式（如 'daily 08:00'、"
            "'weekly mon 09:00'、'interval 30m'）和 tool 名稱。"
        )

    async def handler(invocation: ToolInvocation) -> ToolResult:
        args = invocation.get("arguments") or {}
        session_id = invocation.get("session_id", "")
        route_id = session_id.split("__")[0].replace("-", ":", 1)

        cron_expr = args.get("cron_expr", "").strip()
        tool_name = args.get("tool_name", "").strip()
        description = args.get("description", "").strip()

        if not cron_expr or not tool_name:
            return ToolResult(
                textResultForLlm="需要提供 cron 表達式和 tool 名稱",
                resultType="failure",
            )

        # Validate tool_name against available tools
        available = get_available_tools() if get_available_tools else []
        if available and tool_name not in available:
            return ToolResult(
                textResultForLlm=(
                    f"tool '{tool_name}' 不存在。"
                    f"可用的 tool：{', '.join(available)}"
                ),
                resultType="failure",
            )

        from chatpilot.cron.parser import parse_cron

        try:
            next_run_at = parse_cron(cron_expr)
        except ValueError as e:
            return ToolResult(
                textResultForLlm=f"cron 表達式無效: {e}",
                resultType="failure",
            )

        try:
            schedule_id = await memory_store.save(
                route_id,
                "schedule",
                {
                    "cron_expr": cron_expr,
                    "tool_name": tool_name,
                    "input_data": {"description": description} if description else {},
                    "next_run_at": next_run_at.isoformat(),
                },
            )
            return ToolResult(
                textResultForLlm=(
                    f"已建立排程：{cron_expr} {tool_name}"
                    f"{f' — {description}' if description else ''}"
                    f"（ID: {schedule_id[:8]}，下次執行: {next_run_at.isoformat()}）"
                ),
                resultType="success",
            )
        except Exception as e:
            logger.error("schedule_task_cron failed: %s", e)
            return ToolResult(
                textResultForLlm=f"建立排程失敗: {e}",
                resultType="failure",
            )

    return ToolDefinition(
        name="schedule_task_cron",
        description=_build_description(),
        parameters={
            "type": "object",
            "properties": {
                "cron_expr": {
                    "type": "string",
                    "description": "排程表達式（daily HH:MM / weekly DAY HH:MM / interval Nm）",
                },
                "tool_name": {
                    "type": "string",
                    "description": "要執行的 tool 名稱",
                },
                "description": {
                    "type": "string",
                    "description": "排程說明，作為 tool 的 input_data（選填）",
                },
            },
            "required": ["cron_expr", "tool_name"],
        },
        handler=handler,
        access_level=AccessLevel.GLOBAL,
    )
