"""show_image tool — send an image back to the user via ResponseInjector."""

from __future__ import annotations

import logging
from typing import Any

from copilot.types import ToolInvocation, ToolResult

from chatpilot.core.types import AccessLevel, ToolDefinition

logger = logging.getLogger(__name__)


def _parse_ref(ref: str, adapters: dict) -> tuple[str, str]:
    for platform in sorted(adapters.keys(), key=len, reverse=True):
        prefix = f"{platform}:"
        if ref.startswith(prefix):
            return platform, ref[len(prefix):]

    parts = ref.split(":", 1)
    if len(parts) != 2:
        raise ValueError(f"無效的 ref 格式: {ref}")
    return parts[0], parts[1]


def create_show_image_tool(
    adapters: dict,
    r2_storage: Any,
    response_injector: Any,
) -> ToolDefinition:
    """Create show_image tool.

    Two modes:
    - url: directly inject an existing image URL (floor plans, R2 images)
    - ref: download from platform (LINE), upload to R2, then inject
    """

    async def handler(invocation: ToolInvocation) -> ToolResult:
        args = invocation.get("arguments") or {}
        session_id = invocation.get("session_id", "")
        url = args.get("url", "")
        ref = args.get("ref", "")
        caption = args.get("caption", "")

        if not url and not ref:
            return ToolResult(
                textResultForLlm="需要提供 url 或 ref",
                resultType="failure",
            )

        # Mode 1: direct URL (floor plans, existing R2 images)
        if url:
            if response_injector:
                response_injector.add(session_id, "image", url)
            result = "已準備回傳圖片給使用者"
            if caption:
                result += f"（{caption}）"
            return ToolResult(
                textResultForLlm=result, resultType="success"
            )

        # Mode 2: download from platform ref → upload R2 → inject
        try:
            platform, media_id = _parse_ref(ref, adapters)
        except ValueError:
            return ToolResult(
                textResultForLlm=f"無效的 ref 格式: {ref}",
                resultType="failure",
            )
        adapter = adapters.get(platform)
        if adapter is None or not hasattr(adapter, "download_media"):
            return ToolResult(
                textResultForLlm=f"平台 {platform} 不支援媒體下載",
                resultType="failure",
            )

        data = await adapter.download_media(media_id)
        if data is None:
            return ToolResult(
                textResultForLlm=f"無法下載 {ref}（可能已過期）",
                resultType="failure",
            )

        if r2_storage is None:
            return ToolResult(
                textResultForLlm="R2 storage 未設定，無法回傳圖片",
                resultType="failure",
            )

        try:
            img_url = await r2_storage.upload(data, "image/jpeg", "jpg")
        except Exception as e:
            logger.error("R2 upload failed: %s", e)
            return ToolResult(
                textResultForLlm=f"圖片上傳失敗: {e}",
                resultType="failure",
            )

        if not img_url:
            return ToolResult(
                textResultForLlm="圖片上傳失敗（無 URL）",
                resultType="failure",
            )

        if response_injector:
            response_injector.add(session_id, "image", img_url)

        result = "已準備回傳圖片給使用者"
        if caption:
            result += f"（{caption}）"
        return ToolResult(
            textResultForLlm=result, resultType="success"
        )

    return ToolDefinition(
        name="show_image",
        description=(
            "回傳一張圖片給使用者。兩種用法：\n"
            "1. url: 已有圖片網址（如位置圖 URL）→ 直接回傳\n"
            "2. ref: 平台媒體（如 line:msg_123）→ 下載後回傳\n"
            "提供 url 或 ref 其中一個即可。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "圖片網址（直接回傳）",
                },
                "ref": {
                    "type": "string",
                    "description": "平台媒體 ref（如 line:msg_123）",
                },
                "caption": {
                    "type": "string",
                    "description": "圖片說明（選填）",
                },
            },
        },
        handler=handler,
        access_level=AccessLevel.GLOBAL,
    )
