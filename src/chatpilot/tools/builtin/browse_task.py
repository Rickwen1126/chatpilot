"""browse_task tool — submit async browser search task."""

from __future__ import annotations

import uuid

from copilot.types import ToolInvocation, ToolResult

from chatpilot.core.time_service import TimeService
from chatpilot.core.types import AccessLevel, TaskInfo, ToolDefinition
from chatpilot.tools.session_context import get_session_context


def create_browse_task_tool(scheduler) -> ToolDefinition:
    """Create a browse_task tool that submits async browser search.

    This is an AGENT_TEAM_TRIGGER tool - only chatbots can call it,
    and it enqueues a task to the scheduler for async execution.
    """

    async def handler(invocation: ToolInvocation) -> ToolResult:
        args = invocation.get("arguments") or {}
        query = args.get("query", "")
        chat_route_id = get_session_context(invocation).route_id

        if not query:
            return ToolResult(
                textResultForLlm="請提供搜尋關鍵字",
                resultType="failure",
            )

        task_id = str(uuid.uuid4())
        task = TaskInfo(
            id=task_id,
            created_at=TimeService.get().utc_now(),
            pipeline_name="browser-search",
            input_summary=f"瀏覽器搜尋: {query[:100]}",
            input_data={"query": query},
            chat_route_id=chat_route_id,
        )
        await scheduler.enqueue(task)
        return ToolResult(
            textResultForLlm=f"已提交瀏覽器搜尋任務，ID: {task_id[:8]}。結果會在完成後推送給你。",
            resultType="success",
        )

    return ToolDefinition(
        name="browse_task",
        description=(
            "提交深度瀏覽器搜尋任務。用瀏覽器搜尋 Google 並抓取結果，"
            "適合需要最新資訊或深入搜尋的問題。結果會異步推送回來。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜尋關鍵字",
                },
            },
            "required": ["query"],
        },
        handler=handler,
        access_level=AccessLevel.AGENT_TEAM_TRIGGER,
    )
