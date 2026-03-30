"""Chatbot session — wraps SDK session with chatbot config."""

from __future__ import annotations

import logging

from chatpilot.core.types import ChatbotConfig, Response
from chatpilot.sdk.session import SdkSession

logger = logging.getLogger(__name__)


class ChatbotSession:
    """Per-route chatbot session wrapping an SDK session."""

    def __init__(
        self,
        sdk_session: SdkSession,
        config: ChatbotConfig,
    ) -> None:
        self._session = sdk_session
        self._config = config
        self.broken = False
        self.needs_rebuild = False

    @property
    def model(self) -> str:
        return self._config.model

    @property
    def chatbot_name(self) -> str:
        return self._config.name

    @property
    def session_id(self) -> str:
        return self._session.session_id

    async def send_message(
        self,
        text: str,
        context_prefix: str | None = None,
    ) -> Response:
        """Send a message to the chatbot and get a response."""
        prompt = text
        if context_prefix:
            prompt = f"{context_prefix}\n{text}"

        logger.info("[Chatbot] %s sending (%d chars)", self.chatbot_name, len(prompt))
        try:
            result = await self._session.send_and_wait(
                prompt, timeout=self._config.timeout
            )
            logger.info("[Chatbot] %s got response (%d chars)", self.chatbot_name, len(result))
            return Response(text=result)
        except TimeoutError:
            logger.warning("Chatbot timeout for session %s", self._session.session_id)
            await self._mark_broken()
            return Response(text="處理超時，請稍後再試")
        except Exception as e:
            logger.error(
                "Chatbot error for session %s: %s", self._session.session_id, e
            )
            await self._mark_broken()
            return Response(text="系統暫時不可用，請稍後再試")

    async def _mark_broken(self) -> None:
        """Destroy SDK session and mark as broken for eviction."""
        self.broken = True
        await self.destroy()

    async def destroy(self) -> None:
        await self._session.destroy()
