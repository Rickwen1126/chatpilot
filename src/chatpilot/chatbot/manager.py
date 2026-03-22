"""ChatbotManager — per-route session pool management."""

from __future__ import annotations

import logging

from chatpilot.chatbot.session import ChatbotSession
from chatpilot.core.types import ChatbotConfig
from chatpilot.sdk.session import SdkClient
from chatpilot.tools.factory import ToolFactory

logger = logging.getLogger(__name__)


class ChatbotManager:
    """Manages chatbot sessions per route."""

    def __init__(
        self,
        sdk_client: SdkClient,
        chatbot_configs: dict[str, ChatbotConfig],
        tool_factory: ToolFactory,
    ) -> None:
        self._sdk = sdk_client
        self._configs = chatbot_configs
        self._tool_factory = tool_factory
        self._sessions: dict[str, ChatbotSession] = {}
        self._route_model_overrides: dict[str, str] = {}  # per-route model override

    def update_configs(self, configs: dict[str, ChatbotConfig]) -> None:
        self._configs = configs

    def has_chatbot(self, name: str) -> bool:
        return name in self._configs

    async def get_or_create_session(
        self, route_id: str, chatbot_name: str
    ) -> ChatbotSession:
        """Get existing session or create a new one for the given route."""
        existing = self._sessions.get(route_id)
        if existing and not existing.broken:
            return existing
        if existing and existing.broken:
            self._sessions.pop(route_id, None)
            logger.info("Evicted broken session for route=%s", route_id)

        config = self._configs.get(chatbot_name)
        if config is None:
            raise ValueError(f"Chatbot '{chatbot_name}' not found in config")

        model = self._route_model_overrides.get(route_id, config.model)
        tools = self._tool_factory.get_tools_for_chatbot(config.tools)
        sdk_session = await self._sdk.create_session(
            session_id=route_id,
            model=model,
            system_message=config.system_message,
            tools=tools or None,
        )
        session = ChatbotSession(sdk_session, config)
        self._sessions[route_id] = session
        logger.info("Created chatbot session for route=%s chatbot=%s", route_id, chatbot_name)
        return session

    async def switch_model(self, route_id: str, new_model: str) -> None:
        """Switch model for a route by destroying session and storing override."""
        old_session = self._sessions.pop(route_id, None)
        if old_session:
            await old_session.destroy()
        self._route_model_overrides[route_id] = new_model
        logger.info("Switched model for route=%s to %s", route_id, new_model)

    async def destroy_session(self, route_id: str) -> None:
        session = self._sessions.pop(route_id, None)
        if session:
            await session.destroy()

    async def destroy_all(self) -> None:
        for route_id in list(self._sessions):
            await self.destroy_session(route_id)
