"""Copilot SDK session manager — wraps CopilotClient for session lifecycle."""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)


class SessionManager:
    """Manages Copilot SDK sessions.

    Provides session_id generation and wraps the event-based SDK
    into a simpler send_and_wait interface.

    Uses create_session for first contact and resume_session for
    returning conversations (preserves history, allows model change).
    """

    def __init__(self) -> None:
        self._client = None
        self._known_sessions: set[str] = set()

    @staticmethod
    def get_session_id(platform: str, conversation_id: str | None, user_id: str) -> str:
        key = conversation_id or user_id
        return f"{platform}-{key}"

    async def start(self) -> None:
        try:
            from copilot import CopilotClient

            self._client = CopilotClient()
            await self._client.start()
            logger.info("Copilot SDK client started")
        except Exception as e:
            logger.error("Failed to start Copilot SDK client: %s", e)
            raise

    async def stop(self) -> None:
        if self._client is not None:
            try:
                await self._client.stop()
            except Exception:
                pass
            self._client = None
            self._known_sessions.clear()
            logger.info("Copilot SDK client stopped")

    async def get_or_create_session(self, session_id: str, model: str | None = None):
        """Get existing session or create a new one.

        First call for a session_id → create_session.
        Subsequent calls → resume_session (preserves history, allows model change).
        """
        if self._client is None:
            raise RuntimeError("SessionManager not started. Call start() first.")
        from copilot import PermissionHandler

        if session_id in self._known_sessions:
            config = {
                "session_id": session_id,
                "on_permission_request": PermissionHandler.approve_all,
            }
            if model:
                config["model"] = model
            session = await self._client.resume_session(session_id, config)
            logger.debug("Resumed session %s (model=%s)", session_id, model)
            return session

        config = {
            "session_id": session_id,
            "on_permission_request": PermissionHandler.approve_all,
        }
        if model:
            config["model"] = model
        session = await self._client.create_session(config)
        self._known_sessions.add(session_id)
        logger.debug("Created session %s (model=%s)", session_id, model)
        return session

    async def send_and_wait(self, session, prompt: str, timeout: float = 60.0) -> str:
        done = asyncio.Event()
        result_text = ""
        sid = getattr(session, "session_id", "?")

        def on_event(event):
            nonlocal result_text
            if hasattr(event, "type") and hasattr(event.type, "value"):
                etype = event.type.value
                logger.info("[SDK] %s event=%s", sid, etype)
                if etype == "assistant.message":
                    result_text = event.data.content
                    logger.info(
                        "[SDK] %s assistant msg %d chars: %r",
                        sid,
                        len(result_text),
                        result_text[:80],
                    )
                elif etype == "session.idle":
                    done.set()

        session.on(on_event)
        logger.info("[SDK] %s sending prompt (%d chars)", sid, len(prompt))
        await session.send({"prompt": prompt})
        logger.info("[SDK] %s waiting for idle (timeout=%ss)", sid, timeout)
        await asyncio.wait_for(done.wait(), timeout=timeout)
        logger.info("[SDK] %s done, result=%d chars", sid, len(result_text))
        return result_text


session_manager = SessionManager()
