"""batch_image_analyze tool — analyze multiple images via vision pipeline."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from copilot.types import ToolInvocation, ToolResult

from chatpilot.core.types import AccessLevel, TaskInfo, ToolDefinition

logger = logging.getLogger(__name__)


def create_batch_image_analyze_tool(scheduler: Any) -> ToolDefinition:
    """Create a batch_image_analyze tool (AGENT_TEAM_TRIGGER).

    Enqueues a vision analysis task. The chatbot calls this when
    there are too many images to analyze one-by-one.
    """

    async def handler(invocation: ToolInvocation) -> ToolResult:
        args = invocation.get("arguments") or {}
        session_id = invocation.get("session_id", "")
        route_id = session_id.split("__")[0].replace("-", ":", 1)

        refs = args.get("refs", [])
        prompt = args.get("prompt", "")

        if not refs:
            return ToolResult(
                textResultForLlm="需要提供至少一個圖片 ref",
                resultType="failure",
            )

        if not isinstance(refs, list):
            refs = [refs]

        task = TaskInfo(
            id=str(uuid.uuid4()),
            created_at=datetime.now(timezone.utc),
            pipeline_name="batch-image-vision",
            input_summary=f"分析 {len(refs)} 張照片",
            input_data={
                "refs": refs,
                "prompt": prompt or "",
            },
            chat_route_id=route_id,
        )
        await scheduler.enqueue(task)

        return ToolResult(
            textResultForLlm=(
                f"已提交 {len(refs)} 張照片分析任務（ID: {task.id[:8]}）。"
                "分析完成後會自動回覆結果。"
            ),
            resultType="success",
        )

    return ToolDefinition(
        name="batch_image_analyze",
        description=(
            "批次分析多張照片（>5 張時使用）。"
            "提供圖片的 ref 列表（如 ['line:msg_1', 'line:msg_2']）。"
            "注意：提交後分析在背景執行，結果會自動推送給使用者。"
            "提交後不要自己再用 download_media 下載同一批照片，避免重複。"
            "少於 5 張時請用 download_media 逐張查看，不需要此工具。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "refs": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "圖片 ref 列表（如 line:msg_123）",
                },
                "prompt": {
                    "type": "string",
                    "description": "分析指令（選填，預設辨識物料品牌/品名/數量）",
                },
            },
            "required": ["refs"],
        },
        handler=handler,
        access_level=AccessLevel.AGENT_TEAM_TRIGGER,
    )
