"""task_history tool — query task history via chatbot."""

from __future__ import annotations

from copilot.types import ToolInvocation, ToolResult

from chatpilot.core.types import AccessLevel, ToolDefinition


def create_task_history_tool(scheduler) -> ToolDefinition:
    """Create a task_history tool for querying task history.

    Handler follows SDK ToolHandler signature: (ToolInvocation) -> ToolResult.
    """

    async def handler(invocation: ToolInvocation) -> ToolResult:
        args = invocation.get("arguments") or {}
        action = args.get("action", "list")
        task_id = args.get("task_id", "")
        chat_route_id = invocation.get("session_id", "")

        if action == "detail" and task_id:
            task = await scheduler.get_task(task_id)
            if task is None:
                return ToolResult(
                    textResultForLlm=f"找不到任務 ID: {task_id}",
                    resultType="success",
                )
            lines = [
                f"任務 ID: {task.id[:8]}",
                f"狀態: {task.status.value}",
                f"Pipeline: {task.pipeline_name}",
                f"建立時間: {task.created_at.isoformat()}",
                f"輸入: {task.input_summary}",
            ]
            if task.output_summary:
                lines.append(f"結果: {task.output_summary}")
            if task.error:
                lines.append(f"錯誤: {task.error}")
            if task.duration_ms:
                lines.append(f"耗時: {task.duration_ms}ms")
            return ToolResult(
                textResultForLlm="\n".join(lines),
                resultType="success",
            )

        # Default: list tasks
        tasks = await scheduler.list_tasks(
            chat_route_id=chat_route_id or None, limit=10
        )
        if not tasks:
            return ToolResult(
                textResultForLlm="目前沒有任務記錄",
                resultType="success",
            )
        lines = ["最近任務："]
        for t in tasks:
            summary = t.input_summary[:50]
            lines.append(
                f"  {t.id[:8]} | {t.status.value}"
                f" | {t.pipeline_name} | {summary}"
            )
        return ToolResult(
            textResultForLlm="\n".join(lines),
            resultType="success",
        )

    return ToolDefinition(
        name="task_history",
        description=(
            "查詢任務歷史。action='list' 列出最近任務，"
            "action='detail' + task_id 查詢特定任務。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["list", "detail"],
                    "description": "查詢類型：list 或 detail",
                },
                "task_id": {
                    "type": "string",
                    "description": "任務 ID（action=detail 時必填）",
                },
            },
        },
        handler=handler,
        access_level=AccessLevel.CHATBOT_ONLY,
    )
