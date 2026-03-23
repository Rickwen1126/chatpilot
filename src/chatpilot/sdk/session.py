"""SDK session helper — wraps CopilotClient for session lifecycle."""

from __future__ import annotations

import logging
from typing import Any

from copilot.types import Tool as SdkTool

logger = logging.getLogger(__name__)


class SdkSession:
    """Wrapper around a single Copilot SDK session."""

    def __init__(self, session: Any, session_id: str):
        self._session = session
        self.session_id = session_id

    async def send_and_wait(self, message: str, timeout: float = 60.0) -> str:
        """Send message and wait for assistant response.

        Uses the SDK's built-in send_and_wait which handles
        event listening, idle detection, and timeout internally.

        Raises:
            TimeoutError: If response takes longer than timeout.
        """
        logger.info(
            "[SDK] %s sending (%d chars) timeout=%ss", self.session_id, len(message), timeout
        )
        result = await self._session.send_and_wait(
            {"prompt": message}, timeout=timeout
        )
        logger.info("[SDK] %s got result: %s", self.session_id, type(result))
        if result is None:
            return ""
        content = getattr(result.data, "content", None) or ""
        logger.info("[SDK] %s response: %d chars", self.session_id, len(content))
        return content

    async def destroy(self) -> None:
        """Destroy the underlying SDK session."""
        try:
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
            config["system_message"] = {"mode": "replace", "content": system_message}
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
        system_message: str | None = None,
        tools: list[SdkTool] | None = None,
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
        session = await self._client.resume_session(session_id, config)
        logger.debug("Resumed session %s (model=%s)", session_id, model)
        return SdkSession(session, session_id)

    async def destroy_session(self, session: SdkSession) -> None:
        """Destroy an SDK session."""
        await session.destroy()
