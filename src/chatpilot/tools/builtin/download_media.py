"""download_media tool — download media by platform ref."""

from __future__ import annotations

import base64
import logging
from typing import Any

from pydantic import BaseModel, Field

from chatpilot.core.types import AccessLevel, ToolDefinition

logger = logging.getLogger(__name__)


class DownloadMediaParams(BaseModel):
    ref: str = Field(description="媒體參考 ID，格式為 platform:media_id，例如 line:msg_123")


def create_download_media_tool(adapters: dict) -> ToolDefinition:
    """Create a download_media tool.

    The tool parses the ref to determine platform, finds the adapter,
    and downloads the media content.
    """

    async def handler(invocation: Any) -> Any:
        from copilot.types import ToolResult

        args = invocation.get("arguments") or {}
        ref = args.get("ref", "")

        if ":" not in ref:
            return ToolResult(
                textResultForLlm=f"無效的 ref 格式: {ref}（應為 platform:media_id）",
                resultType="failure",
            )

        platform, media_id = ref.split(":", 1)
        adapter = adapters.get(platform)
        if adapter is None:
            return ToolResult(
                textResultForLlm=f"未知的平台: {platform}",
                resultType="failure",
            )

        if not hasattr(adapter, "download_media"):
            return ToolResult(
                textResultForLlm=f"平台 {platform} 不支援媒體下載",
                resultType="failure",
            )

        data = await adapter.download_media(media_id)
        if data is None:
            return ToolResult(
                textResultForLlm=f"無法下載媒體 {ref}（可能已過期或不存在）",
                resultType="failure",
            )

        b64 = base64.b64encode(data).decode("ascii")
        logger.info("Downloaded media %s (%d bytes)", ref, len(data))

        return ToolResult(
            textResultForLlm=f"已下載圖片 {ref}（{len(data)} bytes）",
            resultType="success",
            binaryResultsForLlm=[
                {"data": b64, "mimeType": "image/jpeg", "type": "image"},
            ],
        )

    return ToolDefinition(
        name="download_media",
        description=(
            "下載圖片或媒體檔案。"
            "當上下文中出現 [圖片 ref:platform:id] 且你需要查看圖片內容時使用。"
            "提供完整的 ref 字串（如 line:msg_123）。"
        ),
        parameters=DownloadMediaParams.model_json_schema(),
        handler=handler,
        access_level=AccessLevel.GLOBAL,
    )
