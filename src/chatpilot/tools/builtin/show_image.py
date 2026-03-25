"""show_image tool — send an image back to the user via ResponseInjector."""

from __future__ import annotations

import logging
from typing import Any

from copilot.types import ToolInvocation, ToolResult

from chatpilot.core.types import AccessLevel, ToolDefinition

logger = logging.getLogger(__name__)


def create_show_image_tool(
    adapters: dict,
    r2_storage: Any,
    response_injector: Any,
) -> ToolDefinition:
    """Create show_image tool.

    Downloads media from platform ref, uploads to R2 for persistent URL,
    injects into response via ResponseInjector so user sees the image.
    """

    async def handler(invocation: ToolInvocation) -> ToolResult:
        args = invocation.get("arguments") or {}
        session_id = invocation.get("session_id", "")
        ref = args.get("ref", "")
        caption = args.get("caption", "")

        if not ref:
            return ToolResult(
                textResultForLlm="需要提供圖片 ref（如 line:msg_123）",
                resultType="failure",
            )

        # Parse ref
        parts = ref.split(":")
        if len(parts) < 2:
            return ToolResult(
                textResultForLlm=f"無效的 ref 格式: {ref}",
                resultType="failure",
            )

        platform, media_id = parts[0], parts[1]
        adapter = adapters.get(platform)
        if adapter is None or not hasattr(adapter, "download_media"):
            return ToolResult(
                textResultForLlm=f"平台 {platform} 不支援媒體下載",
                resultType="failure",
            )

        # Download
        data = await adapter.download_media(media_id)
        if data is None:
            return ToolResult(
                textResultForLlm=f"無法下載 {ref}（可能已過期）",
                resultType="failure",
            )

        # Upload to R2 for persistent URL
        if r2_storage is None:
            return ToolResult(
                textResultForLlm="R2 storage 未設定，無法回傳圖片",
                resultType="failure",
            )

        try:
            url = await r2_storage.upload(data, "image/jpeg", "jpg")
        except Exception as e:
            logger.error("R2 upload failed: %s", e)
            return ToolResult(
                textResultForLlm=f"圖片上傳失敗: {e}",
                resultType="failure",
            )

        if not url:
            return ToolResult(
                textResultForLlm="圖片上傳失敗（無 URL）",
                resultType="failure",
            )

        # Inject image into response
        if response_injector:
            response_injector.add(session_id, "image", url)

        result = "已準備回傳圖片給使用者"
        if caption:
            result += f"（{caption}）"
        return ToolResult(textResultForLlm=result, resultType="success")

    return ToolDefinition(
        name="show_image",
        description=(
            "回傳一張圖片給使用者。"
            "當你需要讓使用者看到某張照片時使用（例如：確認不清楚的物料）。"
            "提供圖片的 ref（如 line:msg_123），系統會下載並回傳。"
            "可附帶 caption 說明（會顯示在文字訊息中，圖片另外發送）。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "ref": {
                    "type": "string",
                    "description": "圖片 ref（如 line:msg_123）",
                },
                "caption": {
                    "type": "string",
                    "description": "圖片說明（選填）",
                },
            },
            "required": ["ref"],
        },
        handler=handler,
        access_level=AccessLevel.GLOBAL,
    )
