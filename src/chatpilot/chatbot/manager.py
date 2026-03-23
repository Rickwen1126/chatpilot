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
        self._route_chatbot_overrides: dict[str, str] = {}

    def update_configs(self, configs: dict[str, ChatbotConfig]) -> None:
        self._configs = configs

    def has_chatbot(self, name: str) -> bool:
        return name in self._configs

    def get_session(self, route_id: str) -> ChatbotSession | None:
        return self._sessions.get(route_id)

    def get_current_chatbot(self, route_id: str) -> str | None:
        """Get the chatbot name for a route (override or None)."""
        return self._route_chatbot_overrides.get(route_id)

    async def get_or_create_session(
        self, route_id: str, chatbot_name: str
    ) -> ChatbotSession:
        """Get existing session or create/resume one."""
        # Apply chatbot override
        chatbot_name = self._route_chatbot_overrides.get(
            route_id, chatbot_name
        )

        existing = self._sessions.get(route_id)

        # Eviction checks
        if existing and existing.broken:
            self._sessions.pop(route_id, None)
            logger.info("Evicted route=%s reason=broken", route_id)
            existing = None

        if existing and existing.needs_rebuild:
            await existing.destroy()
            self._sessions.pop(route_id, None)
            logger.info("Evicted route=%s reason=custom_prompt", route_id)
            existing = None

        if existing:
            return existing

        config = self._configs.get(chatbot_name)
        if config is None:
            raise ValueError(f"Chatbot '{chatbot_name}' not found")

        system_message = await self._build_system_message(
            config.system_message, route_id
        )
        model = self._route_model_overrides.get(route_id, config.model)
        tools = self._tool_factory.get_tools_for_chatbot(config.tools)
        tool_names = [t.name for t in tools] if tools else []
        logger.info(
            "Session setup route=%s chatbot=%s tools=%s",
            route_id, chatbot_name, tool_names,
        )

        # Session ID: route@chatbot (@ separator preserves route_id derivation)
        sdk_session_id = f"{route_id.replace(':', '-')}@{chatbot_name}"

        # Try resume (preserves conversation history for same chatbot)
        try:
            sdk_session = await self._sdk.resume_session(
                session_id=sdk_session_id,
                model=model,
                system_message=system_message,
                tools=tools or None,
            )
            logger.info(
                "Resumed route=%s chatbot=%s", route_id, chatbot_name
            )
        except Exception:
            sdk_session = await self._sdk.create_session(
                session_id=sdk_session_id,
                model=model,
                system_message=system_message,
                tools=tools or None,
            )
            logger.info(
                "Created route=%s chatbot=%s", route_id, chatbot_name
            )

        session = ChatbotSession(sdk_session, config)
        self._sessions[route_id] = session
        return session

    async def _build_system_message(
        self, base: str, route_id: str
    ) -> str:
        if self._memory_store is None:
            return base
        try:
            prompts = await self._memory_store.list(
                route_id, "custom_prompt"
            )
        except Exception:
            return base
        if not prompts:
            return base
        lines = [p["text"] for p in prompts if p.get("text")]
        if not lines:
            return base
        custom_section = "\n- ".join(lines)
        return f"{base}\n\n[使用者偏好]\n- {custom_section}"

    async def switch_chatbot(
        self, route_id: str, chatbot_name: str
    ) -> None:
        """Switch chatbot for a route. Destroys old session, creates fresh."""
        old = self._sessions.pop(route_id, None)
        if old:
            await old.destroy()
        self._route_chatbot_overrides[route_id] = chatbot_name
        logger.info(
            "Switched chatbot route=%s to %s", route_id, chatbot_name
        )

    async def switch_model(self, route_id: str, new_model: str) -> None:
        """Switch model. Destroys session, next message resumes with new model."""
        old = self._sessions.pop(route_id, None)
        if old:
            await old.destroy()
        self._route_model_overrides[route_id] = new_model
        logger.info("Switched model route=%s to %s", route_id, new_model)

    async def destroy_session(self, route_id: str) -> None:
        session = self._sessions.pop(route_id, None)
        if session:
            await session.destroy()

    async def destroy_all(self) -> None:
        for route_id in list(self._sessions):
            await self.destroy_session(route_id)
