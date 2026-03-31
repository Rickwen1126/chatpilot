"""show_image tool — send an image back to the user via ResponseInjector."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from copilot.types import ToolInvocation, ToolResult

from chatpilot.core.types import AccessLevel, ToolDefinition
from chatpilot.files.center import FileHandleCenter
from chatpilot.files.ref_lookup import parse_media_ref
from chatpilot.tools.session_context import get_session_context

logger = logging.getLogger(__name__)


def _guess_upload_format(
    *,
    filename: str | None,
    mime_type: str | None,
    fallback_url: str | None = None,
) -> tuple[str, str]:
    if mime_type:
        mime_type = mime_type.lower()
    if filename:
        suffix = Path(filename).suffix.lower()
        if suffix == ".png":
            return ("image/png", "png")
        if suffix in {".jpg", ".jpeg"}:
            return ("image/jpeg", "jpg")
        if suffix == ".gif":
            return ("image/gif", "gif")
        if suffix == ".webp":
            return ("image/webp", "webp")
    if mime_type == "image/png":
        return ("image/png", "png")
    if mime_type == "image/gif":
        return ("image/gif", "gif")
    if mime_type == "image/webp":
        return ("image/webp", "webp")
    if fallback_url:
        suffix = Path(urlparse(fallback_url).path).suffix.lower()
        if suffix == ".png":
            return ("image/png", "png")
        if suffix == ".gif":
            return ("image/gif", "gif")
        if suffix == ".webp":
            return ("image/webp", "webp")
    return ("image/jpeg", "jpg")


def create_show_image_tool(
    adapters: dict,
    r2_storage: Any,
    response_injector: Any,
    file_handle_center: FileHandleCenter | None = None,
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
        file_id = args.get("file_id", "")
        caption = args.get("caption", "")

        if not url and not ref and not file_id:
            return ToolResult(
                textResultForLlm="需要提供 url、file_id 或 ref",
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

        session_context = None
        if file_handle_center is not None:
            try:
                session_context = get_session_context(invocation)
            except RuntimeError:
                session_context = None

        # Mode 2: governed file_id / ref → local asset → upload R2 → inject
        data: bytes | None = None
        handle = None

        if file_id:
            if file_handle_center is None:
                return ToolResult(
                    textResultForLlm="FileHandleCenter 未設定，無法使用 file_id",
                    resultType="failure",
                )
            if session_context is None:
                return ToolResult(
                    textResultForLlm="缺少 session context，無法驗證 file_id 暴露權限",
                    resultType="failure",
                )
            handle = await file_handle_center.get_handle(file_id)
            if handle is None:
                return ToolResult(
                    textResultForLlm=f"找不到 file_id: {file_id}",
                    resultType="failure",
                )
            if not await file_handle_center.can_expose_to_route(
                file_id=handle.file_id,
                route_id=session_context.route_id,
            ):
                return ToolResult(
                    textResultForLlm="此圖片未被允許對目前 route 暴露",
                    resultType="failure",
                )
            local_path = await file_handle_center.ensure_local(handle.file_id)
            data = Path(local_path).read_bytes()
        else:
            try:
                platform, media_id, _ = parse_media_ref(ref, adapters)
            except ValueError:
                return ToolResult(
                    textResultForLlm=f"無效的 ref 格式: {ref}",
                    resultType="failure",
                )
            adapter = adapters.get(platform)
            if file_handle_center is not None and session_context is not None:
                handle = await file_handle_center.find_source_handle(
                    route_id=session_context.route_id,
                    platform=platform,
                    native_locator=media_id,
                )
                if handle is not None:
                    if not await file_handle_center.can_expose_to_route(
                        file_id=handle.file_id,
                        route_id=session_context.route_id,
                    ):
                        return ToolResult(
                            textResultForLlm="此圖片未被允許對目前 route 暴露",
                            resultType="failure",
                        )
                    local_path = await file_handle_center.ensure_local(handle.file_id)
                    data = Path(local_path).read_bytes()

        if data is None:
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

        upload_mime, upload_ext = _guess_upload_format(
            filename=(handle.filename if handle is not None else None),
            mime_type=(handle.mime_type if handle is not None else None),
            fallback_url=url or None,
        )
        try:
            img_url = await r2_storage.upload(data, upload_mime, upload_ext)
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
        if (
            file_handle_center is not None
            and handle is not None
            and session_context is not None
        ):
            await file_handle_center.add_relation(
                from_file_id=handle.file_id,
                relation_type="shown_in_response",
                subject_type="route",
                subject_id=session_context.route_id,
                metadata={
                    "session_id": session_id,
                    "url": img_url,
                    "caption": caption,
                },
            )

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
            "2. file_id: 已納管的 canonical file → 驗證暴露權限後回傳\n"
            "3. ref: 平台媒體（如 line:msg_123）→ 下載後回傳\n"
            "提供 url、file_id 或 ref 其中一個即可。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "圖片網址（直接回傳）",
                },
                "file_id": {
                    "type": "string",
                    "description": "已納管的 canonical file_id",
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
