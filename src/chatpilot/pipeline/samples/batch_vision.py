"""Batch Image Vision pipeline — analyze multiple images via SDK session."""

from __future__ import annotations

import logging
import uuid

from chatpilot.core.types import NodeOutput
from chatpilot.pipeline.executor import PipelineDefinition
from chatpilot.pipeline.node import PipelineNode
from chatpilot.sdk.session import SdkClient
from chatpilot.tools.factory import ToolFactory

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gpt-5.2"  # SDK 可用最強 vision model，binary tool result OK
DEFAULT_SYSTEM_MESSAGE = (
    "你是一個倉庫物料視覺辨識助手。"
    "你會收到多張照片的 ref，請用 download_media 工具逐張下載查看。"
    "辨識每張照片中的物料：品牌、品名、顏色、規格、數量。"
    "最後用簡潔的中文彙整結果回覆。"
)


class BatchImageVisionNode:
    """Vision analysis — creates SDK session with download_media to see images."""

    def __init__(
        self,
        sdk_client: SdkClient,
        tool_factory: ToolFactory,
        model: str = DEFAULT_MODEL,
    ) -> None:
        self._sdk = sdk_client
        self._tool_factory = tool_factory
        self._model = model

    @property
    def name(self) -> str:
        return "batch-image-vision"

    async def execute(self, input: dict) -> NodeOutput:
        refs = input.get("refs", [])
        prompt = input.get("prompt", "")

        if not refs:
            return NodeOutput(status="error", data={}, error="No image refs")

        session_id = f"pipeline-vision-{uuid.uuid4().hex[:12]}"

        # Get download_media tool for this session (GLOBAL level)
        tools = self._tool_factory.get_tools_for_pipeline(["download_media"])

        # Build prompt with all refs
        refs_list = "\n".join(f"- [圖片 ref:{r}]" for r in refs)
        full_prompt = (
            f"{prompt or '分析以下照片中的物料'}\n\n"
            f"共 {len(refs)} 張照片：\n{refs_list}\n\n"
            "請用 download_media 工具下載每張照片，查看後彙整分析結果。"
        )

        try:
            session = await self._sdk.create_session(
                session_id,
                model=self._model,
                system_message=DEFAULT_SYSTEM_MESSAGE,
                tools=tools or None,
            )
            try:
                result = await session.send_and_wait(
                    full_prompt, timeout=180.0
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
        **kwargs,
    ) -> None:
        self.nodes: list[PipelineNode] = [
            BatchImageVisionNode(sdk_client, tool_factory, **kwargs)
        ]
        self.max_iterations = 1
