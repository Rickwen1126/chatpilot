"""Copilot SDK session manager — wraps CopilotClient for session lifecycle."""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)


class SessionManager:
    """Manages Copilot SDK sessions.

    Provides session_id generation and wraps the event-based SDK
    into a simpler send_and_wait interface.
    """

    def __init__(self) -> None:
        self._client = None

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
            logger.info("Copilot SDK client stopped")

    async def resume_session(self, session_id: str):
        if self._client is None:
            raise RuntimeError("SessionManager not started. Call start() first.")
        return await self._client.create_session(
            {
                "session_id": session_id,
            }
        )

    async def send_and_wait(self, session, prompt: str, timeout: float = 60.0) -> str:
        done = asyncio.Event()
        result_text = ""

        def on_event(event):
            nonlocal result_text
            if hasattr(event, "type") and hasattr(event.type, "value"):
                if event.type.value == "assistant.message":
                    result_text = event.data.content
                elif event.type.value == "session.idle":
                    done.set()

        session.on(on_event)
        await session.send({"prompt": prompt})
        await asyncio.wait_for(done.wait(), timeout=timeout)
        return result_text


session_manager = SessionManager()
