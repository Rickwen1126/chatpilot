"""calendar tool — get current date/time and calendar context."""

from __future__ import annotations

import logging
from datetime import timedelta

from copilot.types import ToolInvocation, ToolResult

from chatpilot.core.time_service import TimeService
from chatpilot.core.types import AccessLevel, ToolDefinition

logger = logging.getLogger(__name__)

_WEEKDAY_MAP = ["週一", "週二", "週三", "週四", "週五", "週六", "週日"]


def create_calendar_tool() -> ToolDefinition:
    """Create calendar tool for date/time queries."""

    async def handler(invocation: ToolInvocation) -> ToolResult:
        ts = TimeService.get()
        now = ts.now()
        today = now.date()
        wd = _WEEKDAY_MAP[today.weekday()]

        # This week (Mon-Sun)
        mon = today - timedelta(days=today.weekday())
        week_lines = []
        for i in range(7):
            d = mon + timedelta(days=i)
            mark = " ← 今天" if d == today else ""
            week_lines.append(
                f"  {_WEEKDAY_MAP[i]} = {d.strftime('%m/%d')}{mark}"
            )

        # Next week
        next_mon = mon + timedelta(weeks=1)
        next_lines = []
        for i in range(7):
            d = next_mon + timedelta(days=i)
            next_lines.append(
                f"  {_WEEKDAY_MAP[i]} = {d.strftime('%m/%d')}"
            )

        result = (
            f"現在：{now.strftime('%Y-%m-%d %H:%M')}（{wd}）\n"
            f"\n本週：\n" + "\n".join(week_lines) +
            "\n\n下週：\n" + "\n".join(next_lines) +
            f"\n\n明天 = {(today + timedelta(1)).strftime('%m/%d')}"
            f"（{_WEEKDAY_MAP[(today + timedelta(1)).weekday()]}）"
            f"\n後天 = {(today + timedelta(2)).strftime('%m/%d')}"
            f"（{_WEEKDAY_MAP[(today + timedelta(2)).weekday()]}）"
        )
        return ToolResult(
            textResultForLlm=result, resultType="success"
        )

    tz_name = TimeService.get().tz_name
    return ToolDefinition(
        name="get_calendar",
        description=(
            "查詢今天日期、本週和下週的日曆。"
            "當需要推算「明天」「下週三」「這週五」等相對日期時使用。"
            f"回傳時間為 {tz_name}。"
        ),
        parameters={"type": "object", "properties": {}},
        handler=handler,
        access_level=AccessLevel.GLOBAL,
    )
