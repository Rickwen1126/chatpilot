"""download_media tool — download media by platform ref."""

from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from chatpilot.core.types import AccessLevel, ToolDefinition
from chatpilot.files.center import FileHandleCenter
from chatpilot.files.ref_lookup import parse_media_ref
from chatpilot.tools.session_context import get_session_context

logger = logging.getLogger(__name__)


class DownloadMediaParams(BaseModel):
    ref: str = Field(description="媒體參考 ID，格式為 platform:media_id，例如 line:msg_123")

def create_download_media_tool(
    adapters: dict,
    file_handle_center: FileHandleCenter | None = None,
) -> ToolDefinition:
    """Create a download_media tool.

    The tool parses the ref to determine platform, finds the adapter,
    and downloads the media content.
    """

    async def handler(invocation: Any) -> Any:
        from copilot.types import ToolResult

        args = invocation.get("arguments") or {}
        ref = args.get("ref", "")

        try:
            platform, media_id, filename = parse_media_ref(ref, adapters)
        except ValueError as e:
            return ToolResult(textResultForLlm=str(e), resultType="failure")
        adapter = adapters.get(platform)
        if adapter is None:
            return ToolResult(
                textResultForLlm=f"未知的平台: {platform}",
                resultType="failure",
            )

        data: bytes | None = None
        handle = None
        session_context = None
        if file_handle_center is not None:
            try:
                session_context = get_session_context(invocation)
            except RuntimeError:
                session_context = None
            if session_context is not None:
                handle = await file_handle_center.find_source_handle(
                    route_id=session_context.route_id,
                    platform=platform,
                    native_locator=media_id,
                )
            if handle is not None:
                local_path = await file_handle_center.ensure_local(handle.file_id)
                data = Path(local_path).read_bytes()

        if data is None:
            if not hasattr(adapter, "download_media"):
                return ToolResult(
                    textResultForLlm=f"平台 {platform} 不支援媒體下載",
                    resultType="failure",
                )
            logger.warning(
                "[file] legacy download_media fallback ref=%s route=%s",
                ref,
                session_context.route_id if session_context is not None else "unknown",
            )
            data = await adapter.download_media(media_id)
        if data is None:
            return ToolResult(
                textResultForLlm=f"無法下載媒體 {ref}（可能已過期或不存在）",
                resultType="failure",
            )

        b64 = base64.b64encode(data).decode("ascii")
        label = (
            handle.filename
            if handle is not None and handle.filename
            else filename or ref
        )
        logger.info("Downloaded media %s (%d bytes)", label, len(data))

        # Detect mime type from filename
        mime = "image/jpeg"
        if filename:
            ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
            mime_map = {
                "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
                "gif": "image/gif", "pdf": "application/pdf",
                "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            }
            mime = mime_map.get(ext, "application/octet-stream")

        return ToolResult(
            textResultForLlm=(
                f"已下載 {label}（{len(data)} bytes）"
                + (
                    f"\nfile_id: {handle.file_id}"
                    if handle is not None
                    else ""
                )
            ),
            resultType="success",
            binaryResultsForLlm=[
                {"data": b64, "mimeType": mime, "type": "image"},
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
