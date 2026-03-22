"""SDK session helper — wraps CopilotClient for session lifecycle."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from copilot.types import Tool as SdkTool

logger = logging.getLogger(__name__)


class ToolCallRecord:
    """Record of a single tool call for audit trail."""

    def __init__(self, tool: str, input: str):
        self.tool = tool
        self.input = input
        self.output: str = ""
        self.success: bool = False


class SdkSession:
    """Wrapper around a single Copilot SDK session."""

    def __init__(self, session: Any, session_id: str):
        self._session = session
        self.session_id = session_id

    async def send_and_wait(self, message: str, timeout: float = 60.0) -> str:
        """Send message and wait for assistant response.

        Raises:
            TimeoutError: If response takes longer than timeout.
            ProcessExitedError: If CLI process crashes.
        """
        done = asyncio.Event()
        result_text = ""
        tool_calls: list[ToolCallRecord] = []
        pending: dict[str, ToolCallRecord] = {}

        def on_event(event: Any) -> None:
            nonlocal result_text
            if not hasattr(event, "type") or not hasattr(event.type, "value"):
                return
            etype = event.type.value

            if etype == "tool.execution_start":
                data = event.data
                call_id = getattr(data, "toolCallId", None) or data.get("toolCallId", "")
                tool_name = getattr(data, "toolName", None) or data.get("toolName", "")
                args = getattr(data, "arguments", None) or data.get("arguments", {})
                record = ToolCallRecord(
                    tool=tool_name,
                    input=json.dumps(args, ensure_ascii=False, default=str)[:200],
                )
                pending[call_id] = record
                tool_calls.append(record)
                logger.info(
                    "Session %s tool_call_start: %s(%s)",
                    self.session_id, tool_name, record.input,
                )

            elif etype == "tool.execution_complete":
                data = event.data
                call_id = getattr(data, "toolCallId", None) or data.get("toolCallId", "")
                success = getattr(data, "success", None)
                if success is None:
                    success = data.get("success", False)
                result = getattr(data, "result", None) or data.get("result", {})
                content = ""
                if isinstance(result, dict):
                    content = result.get("content", "")
                elif hasattr(result, "content"):
                    content = result.content or ""
                record = pending.pop(call_id, None)
                if record:
                    record.output = str(content)[:300]
                    record.success = bool(success)
                logger.info(
                    "Session %s tool_call_done: %s success=%s",
                    self.session_id, record.tool if record else "?", success,
                )

            elif etype == "assistant.message":
                content = getattr(event.data, "content", None)
                if content is None:
                    content = event.data.get("content", "") if isinstance(event.data, dict) else ""
                result_text = content

            elif etype == "session.idle":
                done.set()

        self._session.on(on_event)
        await self._session.send({"prompt": message})
        await asyncio.wait_for(done.wait(), timeout=timeout)
        return result_text

    async def destroy(self) -> None:
        """Destroy the underlying SDK session."""
        try:
            if hasattr(self._session, "destroy"):
                await self._session.destroy()
        except Exception:
            logger.warning("Failed to destroy session %s", self.session_id)


class SdkClient:
    """Manages the Copilot SDK client and session lifecycle."""

    def __init__(self) -> None:
        self._client: Any = None

    async def start(self) -> None:
        """Start the SDK client."""
        from copilot import CopilotClient

        self._client = CopilotClient()
        await self._client.start()
        logger.info("Copilot SDK client started")

    async def stop(self) -> None:
        """Stop the SDK client."""
        if self._client is not None:
            try:
                await self._client.stop()
            except Exception:
                pass
            self._client = None
            logger.info("Copilot SDK client stopped")

    async def create_session(
        self,
        session_id: str,
        *,
        model: str | None = None,
        system_message: str | None = None,
        tools: list[SdkTool] | None = None,
    ) -> SdkSession:
        """Create a new SDK session."""
        if self._client is None:
            raise RuntimeError("SdkClient not started")
        from copilot import PermissionHandler

        config: dict[str, Any] = {
            "session_id": session_id,
            "on_permission_request": PermissionHandler.approve_all,
        }
        if model:
            config["model"] = model
        if system_message:
            config["system_message"] = system_message
        if tools:
            config["tools"] = tools
        session = await self._client.create_session(config)
        logger.debug("Created session %s (model=%s)", session_id, model)
        return SdkSession(session, session_id)

    async def resume_session(
        self,
        session_id: str,
        *,
        model: str | None = None,
    ) -> SdkSession:
        """Resume an existing SDK session."""
        if self._client is None:
            raise RuntimeError("SdkClient not started")
        from copilot import PermissionHandler

        config: dict[str, Any] = {
            "session_id": session_id,
            "on_permission_request": PermissionHandler.approve_all,
        }
        if model:
            config["model"] = model
        session = await self._client.resume_session(session_id, config)
        logger.debug("Resumed session %s (model=%s)", session_id, model)
        return SdkSession(session, session_id)

    async def destroy_session(self, session: SdkSession) -> None:
        """Destroy an SDK session."""
        await session.destroy()
