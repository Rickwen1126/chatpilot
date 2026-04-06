"""SDK session helper — wraps CopilotClient for session lifecycle."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from copilot.types import Tool as SdkTool

logger = logging.getLogger(__name__)


class SdkSession:
    """Wrapper around a single Copilot SDK session."""

    def __init__(self, session: Any, session_id: str):
        self._session = session
        self.session_id = session_id
        self._attach_event_logger()

    def _attach_event_logger(self) -> None:
        """Attach event listener for debug logging. Non-blocking."""
        try:
            sid = self.session_id

            def _on_event(event: Any) -> None:
                etype = getattr(event, "type", "?")
                data = getattr(event, "data", None)
                # Tool calls
                if etype == "assistant.message" and data:
                    tool_reqs = getattr(data, "toolRequests", None) or (
                        data.get("toolRequests") if isinstance(data, dict) else None
                    )
                    if tool_reqs:
                        for t in tool_reqs:
                            _d = isinstance(t, dict)
                            name = t.get("name", "?") if _d else getattr(t, "name", "?")
                            args = t.get("arguments", {}) if _d else getattr(t, "arguments", {})
                            logger.info("[event] %s tool_call: %s(%s)", sid, name, args)
                        return
                    _d = isinstance(data, dict)
                    content = data.get("content", "") if _d else getattr(data, "content", "")
                    if content:
                        preview = content[:80].replace("\n", " ")
                        logger.info("[event] %s assistant: %s...", sid, preview)
                        return
                # Tool results
                if etype == "tool.execution_complete" and data:
                    _d = isinstance(data, dict)
                    name = data.get("toolName", "?") if _d else getattr(data, "toolName", "?")
                    success = data.get("success", "?") if _d else getattr(data, "success", "?")
                    logger.info("[event] %s tool_result: %s ok=%s", sid, name, success)
                    return
                # Errors
                if "error" in str(etype).lower():
                    logger.warning("[event] %s %s: %s", sid, etype, data)
                    return
                # Other events (debug level to avoid noise)
                logger.debug("[event] %s %s", sid, etype)

            self._session.on(_on_event)
        except Exception:
            logger.debug("Event logger not attached for %s", self.session_id)

    async def send_and_wait(self, message: str, timeout: float = 60.0) -> str:
        """Send message and wait for assistant response.

        Uses the SDK's built-in send_and_wait which handles
        event listening, idle detection, and timeout internally.

        Raises:
            TimeoutError: If response takes longer than timeout.
        """
        prompt_preview = message[:150].replace("\n", " ")
        logger.info(
            "[SDK] %s sending (%d chars) timeout=%ss prompt=%s",
            self.session_id, len(message), timeout, prompt_preview,
        )
        return await self._send_and_wait_impl(
            message,
            timeout=timeout,
        )

    async def send_and_wait_with_attachments(
        self,
        message: str,
        *,
        attachments: list[dict[str, str]],
        timeout: float = 60.0,
    ) -> str:
        """Send message with local file attachments and wait for response."""
        return await self._send_and_wait_impl(
            message,
            attachments=attachments,
            timeout=timeout,
        )

    async def _send_and_wait_impl(
        self,
        message: str,
        *,
        attachments: list[dict[str, str]] | None = None,
        timeout: float = 60.0,
    ) -> str:
        payload: dict[str, Any] = {"prompt": message}
        if attachments:
            payload["attachments"] = attachments
            logger.info(
                "[SDK] %s attachments count=%d names=%s",
                self.session_id,
                len(attachments),
                [Path(item.get("path", "")).name for item in attachments],
            )
        try:
            result = await self._session.send_and_wait(payload, timeout=timeout)
        except TimeoutError:
            logger.warning(
                "[SDK] %s send_and_wait timeout timeout=%ss attachments=%d",
                self.session_id,
                timeout,
                len(attachments or []),
            )
            raise
        except Exception as exc:
            logger.exception(
                "[SDK] %s send_and_wait failed type=%s timeout=%ss attachments=%d",
                self.session_id,
                type(exc).__name__,
                timeout,
                len(attachments or []),
            )
            raise
        logger.info("[SDK] %s got result: %s", self.session_id, type(result))
        if result is None:
            logger.warning("[SDK] %s response is None", self.session_id)
            return ""
        content = getattr(result.data, "content", None) or ""
        response_preview = content[:300].replace("\n", " ")
        logger.info(
            "[SDK] %s response (%d chars): %s",
            self.session_id, len(content), response_preview,
        )
        return content

    async def destroy(self) -> None:
        """Destroy the underlying SDK session."""
        try:
            await self._session.destroy()
        except Exception:
            logger.warning("Failed to destroy session %s", self.session_id)

    async def get_current_model(self) -> str | None:
        """Return the SDK runtime model when the backend exposes it."""
        rpc = getattr(self._session, "rpc", None)
        model_rpc = getattr(rpc, "model", None)
        getter = getattr(model_rpc, "get_current", None)
        if getter is None:
            return None
        try:
            current = await getter()
        except Exception:
            logger.debug(
                "[SDK] %s get_current_model unavailable",
                self.session_id,
                exc_info=True,
            )
            return None
        if current is None:
            return None
        if isinstance(current, str):
            return current
        if isinstance(current, dict):
            return (
                current.get("id")
                or current.get("model")
                or current.get("name")
            )
        return (
            getattr(current, "id", None)
            or getattr(current, "model", None)
            or getattr(current, "name", None)
        )


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
        working_directory: str | None = None,
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
            config["system_message"] = {"mode": "replace", "content": system_message}
        if tools:
            config["tools"] = tools
        if working_directory:
            config["working_directory"] = working_directory
        session = await self._client.create_session(config)
        logger.info(
            "Created SDK session %s (model=%s, workdir=%s)",
            session_id, model, working_directory,
        )
        return SdkSession(session, session_id)

    async def resume_session(
        self,
        session_id: str,
        *,
        model: str | None = None,
        system_message: str | None = None,
        tools: list[SdkTool] | None = None,
        working_directory: str | None = None,
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
        if system_message:
            config["system_message"] = {
                "mode": "replace", "content": system_message
            }
        if tools:
            config["tools"] = tools
        if working_directory:
            config["working_directory"] = working_directory
        session = await self._client.resume_session(session_id, config)
        logger.info(
            "Resumed SDK session %s (model=%s, workdir=%s)",
            session_id, model, working_directory,
        )
        return SdkSession(session, session_id)

    async def destroy_session(self, session: SdkSession) -> None:
        """Destroy an SDK session."""
        await session.destroy()
