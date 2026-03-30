"""submit_task tool — creates and enqueues an async task."""

from __future__ import annotations

import uuid

from copilot.types import ToolInvocation, ToolResult

from chatpilot.core.time_service import TimeService
from chatpilot.core.types import AccessLevel, TaskInfo, ToolDefinition
from chatpilot.tools.session_context import get_session_context


def create_submit_task_tool(scheduler, pipeline_name: str = "echo") -> ToolDefinition:
    """Create a submit_task tool definition.

    Handler follows SDK ToolHandler signature: (ToolInvocation) -> ToolResult.
    """

    async def handler(invocation: ToolInvocation) -> ToolResult:
        args = invocation.get("arguments") or {}
        task_description = args.get("task_description", "")
        chat_route_id = get_session_context(invocation).route_id

        task_id = str(uuid.uuid4())
        task = TaskInfo(
            id=task_id,
            created_at=TimeService.get().utc_now(),
            pipeline_name=args.get("pipeline", pipeline_name),
            input_summary=task_description[:200],
            input_data={"description": task_description},
            chat_route_id=chat_route_id,
        )
        await scheduler.enqueue(task)
        return ToolResult(
            textResultForLlm=f"任務已排定，ID: {task_id[:8]}",
            resultType="success",
        )

    return ToolDefinition(
        name="submit_task",
        description=(
            "提交一個異步任務給 agent team 執行。"
            "提供任務描述，系統會在背景處理並回報結果。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "task_description": {
                    "type": "string",
                    "description": "任務描述",
                },
            },
            "required": ["task_description"],
        },
        handler=handler,
        access_level=AccessLevel.AGENT_TEAM_TRIGGER,
    )
