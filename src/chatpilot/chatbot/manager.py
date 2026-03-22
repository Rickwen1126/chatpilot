"""ChatbotManager — per-route session pool management."""

from __future__ import annotations

import logging
from typing import Any

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
        memory_store: Any = None,
    ) -> None:
        self._sdk = sdk_client
        self._configs = chatbot_configs
        self._tool_factory = tool_factory
        self._memory_store = memory_store
        self._sessions: dict[str, ChatbotSession] = {}
        self._route_model_overrides: dict[str, str] = {}

    def update_configs(self, configs: dict[str, ChatbotConfig]) -> None:
        self._configs = configs

    def has_chatbot(self, name: str) -> bool:
        return name in self._configs

    def get_session(self, route_id: str) -> ChatbotSession | None:
        """Get existing session by route_id (for needs_rebuild marking)."""
        return self._sessions.get(route_id)

    async def get_or_create_session(
        self, route_id: str, chatbot_name: str
    ) -> ChatbotSession:
        """Get existing session or create a new one."""
        existing = self._sessions.get(route_id)

        # Check eviction flags
        if existing and existing.broken:
            self._sessions.pop(route_id, None)
            logger.info(
                "Evicted session route=%s reason=broken", route_id
            )
            existing = None

        if existing and existing.needs_rebuild:
            await existing.destroy()
            self._sessions.pop(route_id, None)
            logger.info(
                "Evicted session route=%s reason=custom_prompt_updated",
                route_id,
            )
            existing = None

        if existing:
            return existing

        config = self._configs.get(chatbot_name)
        if config is None:
            raise ValueError(
                f"Chatbot '{chatbot_name}' not found in config"
            )

        # Build system_message with custom_prompts
        system_message = await self._build_system_message(
            config.system_message, route_id
        )

        model = self._route_model_overrides.get(route_id, config.model)
        tools = self._tool_factory.get_tools_for_chatbot(config.tools)
        sdk_session_id = route_id.replace(":", "-")
        sdk_session = await self._sdk.create_session(
            session_id=sdk_session_id,
            model=model,
            system_message=system_message,
            tools=tools or None,
        )
        session = ChatbotSession(sdk_session, config)
        self._sessions[route_id] = session
        logger.info(
            "Created session route=%s chatbot=%s",
            route_id, chatbot_name,
        )
        return session

    async def _build_system_message(
        self, base: str, route_id: str
    ) -> str:
        """Merge base system_message with custom_prompts from memory."""
        if self._memory_store is None:
            return base

        try:
            prompts = await self._memory_store.list(
                route_id, "custom_prompt"
            )
        except Exception:
            logger.warning(
                "Failed to load custom_prompts for %s", route_id
            )
            return base

        if not prompts:
            return base

        lines = [p["text"] for p in prompts if p.get("text")]
        if not lines:
            return base

        custom_section = "\n- ".join(lines)
        return f"{base}\n\n[使用者偏好]\n- {custom_section}"

    async def switch_model(self, route_id: str, new_model: str) -> None:
        old_session = self._sessions.pop(route_id, None)
        if old_session:
            await old_session.destroy()
        self._route_model_overrides[route_id] = new_model
        logger.info("Switched model route=%s to %s", route_id, new_model)

    async def destroy_session(self, route_id: str) -> None:
        session = self._sessions.pop(route_id, None)
        if session:
            await session.destroy()

    async def destroy_all(self) -> None:
        for route_id in list(self._sessions):
            await self.destroy_session(route_id)
