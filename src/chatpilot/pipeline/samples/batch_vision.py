"""Batch Image Vision pipeline — analyze multiple images via SDK session."""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

from chatpilot.core.types import NodeOutput
from chatpilot.files.center import FileHandleCenter
from chatpilot.files.ref_lookup import parse_media_ref
from chatpilot.pipeline.executor import PipelineDefinition
from chatpilot.pipeline.node import PipelineNode
from chatpilot.sdk.session import SdkClient
from chatpilot.tools.factory import ToolFactory

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gpt-5.2"
DEFAULT_SYSTEM_MESSAGE = (
    "你是一個倉庫物料視覺辨識助手。"
    "你會收到多張圖片附件。"
    "辨識每張照片中的物料：品牌、品名、顏色、規格、數量。"
    "最後用簡潔的中文彙整結果回覆。"
)


class BatchImageVisionNode:
    """Vision analysis — creates SDK session with download_media to see images."""

    def __init__(
        self,
        sdk_client: SdkClient,
        tool_factory: ToolFactory,
        file_handle_center: FileHandleCenter,
        adapters: dict,
        model: str = DEFAULT_MODEL,
    ) -> None:
        self._sdk = sdk_client
        self._tool_factory = tool_factory
        self._file_handle_center = file_handle_center
        self._adapters = adapters
        self._model = model

    @property
    def name(self) -> str:
        return "batch-image-vision"

    async def execute(self, input: dict) -> NodeOutput:
        refs = input.get("refs", [])
        prompt = input.get("prompt", "")
        route_id = input.get("route_id", "")

        if not refs:
            return NodeOutput(status="error", data={}, error="No image refs")
        if not route_id:
            return NodeOutput(status="error", data={}, error="Missing route_id")

        session_id = f"pipeline-vision-{uuid.uuid4().hex[:12]}"
        attachments: list[dict[str, str]] = []
        refs_list: list[str] = []
        file_ids: list[str] = []
        for index, ref in enumerate(refs, 1):
            try:
                platform, native_locator, _ = parse_media_ref(ref, self._adapters)
            except ValueError as e:
                return NodeOutput(status="error", data={}, error=str(e))
            handle = await self._file_handle_center.find_source_handle(
                route_id=route_id,
                platform=platform,
                native_locator=native_locator,
            )
            if handle is None:
                return NodeOutput(
                    status="error",
                    data={},
                    error=f"FileHandleCenter missing canonical file for ref: {ref}",
                )
            local_path = await self._file_handle_center.ensure_local(handle.file_id)
            logger.info(
                "[vision] route=%s ref=%s file_id=%s local=%s",
                route_id,
                ref,
                handle.file_id,
                local_path,
            )
            attachments.append({"type": "file", "path": local_path})
            file_ids.append(handle.file_id)
            refs_list.append(f"- 圖片 {index}: {handle.filename or ref}")

        full_prompt = (
            f"{prompt or '分析以下照片中的物料'}\n\n"
            f"共 {len(refs)} 張照片附件：\n" + "\n".join(refs_list) + "\n\n"
            "請直接查看附件中的每張照片，彙整分析結果。"
        )
        logger.info(
            "[vision] session=%s route=%s attachments=%d file_ids=%s files=%s",
            session_id,
            route_id,
            len(attachments),
            file_ids,
            [Path(item["path"]).name for item in attachments],
        )

        try:
            session = await self._sdk.create_session(
                session_id,
                model=self._model,
                system_message=DEFAULT_SYSTEM_MESSAGE,
            )
            try:
                result = await session.send_and_wait_with_attachments(
                    full_prompt,
                    attachments=attachments,
                    timeout=180.0,
                )
                logger.info(
                    "[vision] session=%s completed route=%s total=%d",
                    session_id,
                    route_id,
                    len(refs),
                )
                return NodeOutput(
                    status="success",
                    data={
                        "analysis": result,
                        "total": len(refs),
                    },
                )
            finally:
                await session.destroy()
        except Exception as e:
            logger.exception("BatchImageVisionNode failed")
            return NodeOutput(status="error", data={}, error=str(e))


class BatchImageVisionPipeline(PipelineDefinition):
    """Batch image analysis via SDK session with vision model."""

    name = "batch-image-vision"

    def __init__(
        self,
        sdk_client: SdkClient,
        tool_factory: ToolFactory,
        file_handle_center: FileHandleCenter,
        adapters: dict,
        **kwargs,
    ) -> None:
        self.nodes: list[PipelineNode] = [
            BatchImageVisionNode(
                sdk_client,
                tool_factory,
                file_handle_center,
                adapters,
                **kwargs,
            )
        ]
        self.max_iterations = 1
