"""observe_image_ref tool — observer-only single image analysis."""

from __future__ import annotations

import logging
import tempfile
import uuid
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from chatpilot.core.types import AccessLevel, ToolDefinition
from chatpilot.files.center import FileHandleCenter
from chatpilot.files.ref_lookup import parse_media_ref
from chatpilot.sdk.session import SdkClient
from chatpilot.tools.session_context import get_session_context

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gpt-5.4"
DEFAULT_SYSTEM_MESSAGE = (
    "你是 observer image inspection worker，不是聊天助理。\n"
    "你只根據圖片中實際可見的內容回覆，禁止腦補。\n"
    "請用精簡中文描述與背景整理有關的可觀察事實，例如：人物是否在場、施工狀態、物料、數量線索、現場成果。\n"
    "若圖片資訊不足，就直接說看不清或無法判定，不要編造。"
)


class ObserveImageRefParams(BaseModel):
    image_ref: str = Field(
        description="圖片參考 ID，格式為 platform:native_locator，例如 line:demo:img123"
    )


def create_observe_image_ref_tool(
    sdk_client: SdkClient,
    adapters: dict,
    file_handle_center: FileHandleCenter | None = None,
) -> ToolDefinition:
    """Create observer-only single image analysis tool."""

    async def handler(invocation: Any) -> Any:
        from copilot.types import ToolResult

        args = invocation.get("arguments") or {}
        image_ref = str(args.get("image_ref", "")).strip()
        if not image_ref:
            return ToolResult(
                textResultForLlm="缺少 image_ref",
                resultType="failure",
            )

        try:
            session_context = get_session_context(invocation)
        except RuntimeError as exc:
            return ToolResult(textResultForLlm=str(exc), resultType="failure")

        try:
            platform, native_locator, filename = parse_media_ref(image_ref, adapters)
        except ValueError as exc:
            return ToolResult(textResultForLlm=str(exc), resultType="failure")

        adapter = adapters.get(platform)
        if adapter is None:
            return ToolResult(
                textResultForLlm=f"未知的平台: {platform}",
                resultType="failure",
            )

        temp_path: Path | None = None
        local_path: str | None = None

        try:
            if file_handle_center is None:
                return ToolResult(
                    textResultForLlm="observer 圖片分析未配置 file handle center",
                    resultType="failure",
                )

            handle = await file_handle_center.find_source_handle(
                route_id=session_context.route_id,
                platform=platform,
                native_locator=native_locator,
            )
            if handle is None:
                return ToolResult(
                    textResultForLlm=(
                        "找不到目前 route 已註冊的圖片 ref: "
                        f"{image_ref}"
                    ),
                    resultType="failure",
                )

            local_path = await file_handle_center.ensure_local(handle.file_id)
            if local_path is None:
                if not hasattr(adapter, "download_media"):
                    return ToolResult(
                        textResultForLlm=f"平台 {platform} 不支援圖片下載",
                        resultType="failure",
                    )
                data = await adapter.download_media(native_locator)
                if data is None:
                    return ToolResult(
                        textResultForLlm=f"無法下載圖片 {image_ref}",
                        resultType="failure",
                    )
                suffix = Path(filename or "source.bin").suffix or ".bin"
                with tempfile.NamedTemporaryFile(
                    prefix="observer-image-",
                    suffix=suffix,
                    delete=False,
                ) as fp:
                    fp.write(data)
                    temp_path = Path(fp.name)
                    local_path = fp.name

            vision_sid = f"observer-image-{uuid.uuid4().hex[:8]}"
            session = await sdk_client.create_session(
                vision_sid,
                model=DEFAULT_MODEL,
                system_message=DEFAULT_SYSTEM_MESSAGE,
            )
            try:
                result = await session.send_and_wait_with_attachments(
                    (
                        "請直接查看這張圖片，回覆 2 到 5 句精簡中文描述。"
                        "只保留與背景整理有關的具體可觀察事實；"
                        "若無法判定，就明說不確定。"
                    ),
                    attachments=[{"type": "file", "path": local_path}],
                    timeout=120.0,
                )
            finally:
                await session.destroy()

            text = result.strip()
            if not text:
                return ToolResult(
                    textResultForLlm="圖片分析結果為空",
                    resultType="failure",
                )
            return ToolResult(
                textResultForLlm=text,
                resultType="success",
            )
        except Exception as exc:
            logger.exception("observe_image_ref failed ref=%s", image_ref)
            return ToolResult(
                textResultForLlm=f"圖片分析失敗: {type(exc).__name__}: {exc}",
                resultType="failure",
            )
        finally:
            if temp_path is not None and temp_path.exists():
                temp_path.unlink(missing_ok=True)

    return ToolDefinition(
        name="observe_image_ref",
        description=(
            "observer worker 專用圖片分析工具。"
            "當 observation batch 中出現 [圖片 ref:...]，且圖片內容有助於整理背景知識時使用。"
            "提供完整 image_ref，如 line:demo:img123。"
        ),
        parameters=ObserveImageRefParams.model_json_schema(),
        handler=handler,
        access_level=AccessLevel.OBSERVER_ONLY,
    )
