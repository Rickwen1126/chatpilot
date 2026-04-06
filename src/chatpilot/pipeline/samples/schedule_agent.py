"""Schedule Agent pipeline — executes delegated tasks with chatbot tools.

Unlike general-agent (web_search only), schedule-agent inherits the tools
of the chatbot that created the schedule, so a disposable pipeline actor can
operate on behalf of the original target route.
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

from chatpilot.core.types import NodeOutput, SessionContext
from chatpilot.pipeline.executor import PipelineDefinition
from chatpilot.pipeline.node import PipelineNode
from chatpilot.sdk.session import SdkClient
from chatpilot.tools.factory import ToolFactory
from chatpilot.tools.session_context import split_route_id

logger = logging.getLogger(__name__)

DEFAULT_WORKSPACE_ROOT = "data/workspace"
DEFAULT_SYSTEM_MESSAGE = (
    "你是排程任務代理，負責執行定時排程指派給你的任務。"
    "用工具完成任務後，用簡潔的中文回覆結果。"
    "直接回報結果，不要描述你「會」做什麼。"
)


class ScheduleAgentNode:
    """Delegate agent that uses chatbot tools against a target route context."""

    def __init__(
        self,
        sdk_client: SdkClient,
        tool_factory: ToolFactory | None = None,
        model: str = "gpt-5.4",
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
        return "schedule-agent"

    def _resolve_workdir(self, session_id: str) -> str:
        if self._config_workdir:
            path = Path(self._config_workdir)
        else:
            path = Path(DEFAULT_WORKSPACE_ROOT) / session_id
        path.mkdir(parents=True, exist_ok=True)
        return str(path.resolve())

    async def execute(self, input: dict) -> NodeOutput:
        prompt = input.get("description", str(input))
        session_id = f"schedule-agent-{uuid.uuid4().hex[:12]}"
        workdir = self._resolve_workdir(session_id)
        target_route_id = str(input.get("route_id", "")).strip()
        origin_chatbot_name = str(input.get("chatbot_name", "")).strip()

        from chatpilot.core.time_service import TimeService

        system_msg = (
            f"{self._system_message}\n\n"
            f"{TimeService.get().system_prompt_hint()}\n\n"
            f"[工作目錄]\n你的工作目錄是 {workdir}，"
            "如果需要暫存或輸出檔案，請放在這個目錄下。"
        )

        # Use chatbot's tools from input_data (injected by CronScheduler).
        # Filter out AGENT_TEAM_TRIGGER / CHATBOT_ONLY tools — pipeline
        # cannot use those (recursion guard). They are silently skipped.
        # `chatbot_name` here means the chatbot that created/delegated the job,
        # not the identity of this disposable schedule-agent session.
        tools = None
        if self._tool_factory:
            chatbot_tools = input.get("chatbot_tools", [])
            try:
                if chatbot_tools:
                    # Filter to pipeline-safe tools only (GLOBAL + AGENT_TEAM_ONLY)
                    from chatpilot.core.types import AccessLevel

                    safe_tools = []
                    for t in chatbot_tools:
                        reg = self._tool_factory._registry
                        defn = reg.get(t) if reg.has(t) else None
                        if defn and defn.access_level in (
                            AccessLevel.GLOBAL, AccessLevel.AGENT_TEAM_ONLY
                        ):
                            safe_tools.append(t)
                    tools = self._tool_factory.get_tools_for_pipeline(
                        safe_tools
                    ) if safe_tools else None
                    logger.info(
                        "[schedule-agent] delegated_by=%s target_route=%s tools=%s (from %s)",
                        origin_chatbot_name,
                        target_route_id or "?",
                        safe_tools,
                        chatbot_tools,
                    )
                else:
                    # Fallback: no chatbot tools → web_search only
                    tools = self._tool_factory.get_tools_for_pipeline(
                        ["web_search"]
                    )
                    logger.warning(
                        "[schedule-agent] no chatbot_tools in input, "
                        "falling back to web_search"
                    )
            except Exception:
                logger.exception("[schedule-agent] failed to resolve tools")

        registry = (
            self._tool_factory.session_context_registry
            if self._tool_factory is not None
            else None
        )
        if registry is not None and target_route_id:
            platform, conversation_id = split_route_id(target_route_id)
            registry.register(
                SessionContext(
                    sdk_session_id=session_id,
                    route_id=target_route_id,
                    platform=platform,
                    conversation_id=conversation_id,
                    chatbot_name=origin_chatbot_name,
                ),
                persist_metadata=False,
            )

        try:
            session = await self._sdk_client.create_session(
                session_id,
                model=self._model,
                system_message=system_msg,
                tools=tools or None,
                working_directory=workdir,
            )
            try:
                result = await session.send_and_wait(prompt, timeout=300.0)
                return NodeOutput(
                    status="success",
                    data={"result": result, "prompt": prompt},
                )
            finally:
                await session.destroy()
        except Exception as e:
            logger.exception("[schedule-agent] failed")
            return NodeOutput(status="error", data={}, error=str(e))
        finally:
            if registry is not None:
                registry.unregister(session_id)


class ScheduleAgentPipeline(PipelineDefinition):
    """Schedule agent pipeline — registered as 'schedule-agent'."""

    name = "schedule-agent"

    def __init__(
        self,
        sdk_client: SdkClient,
        tool_factory: ToolFactory | None = None,
        **kwargs,
    ) -> None:
        self.nodes: list[PipelineNode] = [
            ScheduleAgentNode(sdk_client, tool_factory, **kwargs)
        ]
        self.max_iterations = 1
