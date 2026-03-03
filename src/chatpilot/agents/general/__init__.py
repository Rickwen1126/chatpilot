"""General agent — default Copilot SDK-powered conversational agent."""

from __future__ import annotations

import logging

from chatpilot.core.errors import AgentError
from chatpilot.core.types import Message, Response
from chatpilot.sdk.session_manager import session_manager

logger = logging.getLogger(__name__)


class GeneralAgent:
    """Default agent that delegates to Copilot SDK."""

    @property
    def name(self) -> str:
        return "general-agent"

    async def handle(
        self, message: Message, session_id: str, model: str | None = None
    ) -> Response:
        try:
            session = await session_manager.get_or_create_session(
                session_id, model=model
            )
            result = await session_manager.send_and_wait(session, message.text)
            return Response(text=result)
        except Exception as e:
            logger.error("GeneralAgent error: %s", e)
            raise AgentError(
                "抱歉，處理時發生錯誤，請稍後再試。",
                cause=e,
            ) from e


general_agent = GeneralAgent()
