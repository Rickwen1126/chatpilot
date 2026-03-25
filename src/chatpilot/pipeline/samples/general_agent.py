"""General Agent pipeline — LLM agent with tools via SDK session."""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

from chatpilot.core.types import NodeOutput
from chatpilot.pipeline.executor import PipelineDefinition
from chatpilot.pipeline.node import PipelineNode
from chatpilot.sdk.session import SdkClient
from chatpilot.tools.factory import ToolFactory

logger = logging.getLogger(__name__)

DEFAULT_WORKSPACE_ROOT = "data/workspace"
DEFAULT_SYSTEM_MESSAGE = (
    "你是一個通用任務代理，負責執行指派給你的任務。"
    "完成任務後，用簡潔的中文回覆結果。"
)


class GeneralAgentNode:
    """LLM agent — creates a disposable SDK session to process tasks."""

    def __init__(
        self,
        sdk_client: SdkClient,
        tool_factory: ToolFactory | None = None,
        model: str = "gpt-4.1",
        system_message: str = DEFAULT_SYSTEM_MESSAGE,
        workdir: str | None = None,
    ) -> None:
        self._sdk_client = sdk_client
        self._tool_factory = tool_factory
        self._model = model
        self._system_message = system_message
        self._config_workdir = workdir

    @property
    def name(self) -> str:
        return "general-agent"

    def _resolve_workdir(self, session_id: str) -> str:
        if self._config_workdir:
            path = Path(self._config_workdir)
        else:
            path = Path(DEFAULT_WORKSPACE_ROOT) / session_id
        path.mkdir(parents=True, exist_ok=True)
        return str(path.resolve())

    async def execute(self, input: dict) -> NodeOutput:
        prompt = input.get("description", str(input))
        session_id = f"pipeline-agent-{uuid.uuid4().hex[:12]}"
        workdir = self._resolve_workdir(session_id)

        system_msg = (
            f"{self._system_message}\n\n"
            f"[工作目錄]\n你的工作目錄是 {workdir}，"
            "如果需要暫存或輸出檔案，請放在這個目錄下。"
        )

        # Get tools for pipeline (web_search etc.)
        tools = None
        if self._tool_factory:
            try:
                tools = self._tool_factory.get_tools_for_pipeline(
                    ["web_search"]
                )
            except Exception:
                pass

        try:
            session = await self._sdk_client.create_session(
                session_id,
                model=self._model,
                system_message=system_msg,
                tools=tools or None,
                working_directory=workdir,
            )
            try:
                result = await session.send_and_wait(prompt, timeout=120.0)
                return NodeOutput(
                    status="success",
                    data={"result": result, "prompt": prompt},
                )
            finally:
                await session.destroy()
        except Exception as e:
            logger.exception("GeneralAgentNode failed")
            return NodeOutput(status="error", data={}, error=str(e))


class GeneralAgentPipeline(PipelineDefinition):
    """LLM agent pipeline — same level as echo/browser-search."""

    name = "general-agent"

    def __init__(
        self,
        sdk_client: SdkClient,
        tool_factory: ToolFactory | None = None,
        **kwargs,
    ) -> None:
        self.nodes: list[PipelineNode] = [
            GeneralAgentNode(sdk_client, tool_factory, **kwargs)
        ]
        self.max_iterations = 1
