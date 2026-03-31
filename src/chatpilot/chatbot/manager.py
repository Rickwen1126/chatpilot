"""ChatbotManager — per-route session pool management."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from chatpilot.chatbot.session import ChatbotSession
from chatpilot.core.types import ChatbotConfig, SessionContext
from chatpilot.sdk.session import SdkClient
from chatpilot.tools.factory import ToolFactory
from chatpilot.tools.session_context import (
    SessionContextRegistry,
    build_sdk_session_id,
    split_route_id,
)

DEFAULT_WORKSPACE_ROOT = "data/workspace"

logger = logging.getLogger(__name__)


class ChatbotManager:
    """Manages chatbot sessions per route."""

    def __init__(
        self,
        sdk_client: SdkClient,
        chatbot_configs: dict[str, ChatbotConfig],
        tool_factory: ToolFactory,
        memory_store: Any = None,
        session_context_registry: SessionContextRegistry | None = None,
    ) -> None:
        self._sdk = sdk_client
        self._configs = chatbot_configs
        self._tool_factory = tool_factory
        self._memory_store = memory_store
        self._session_context_registry = (
            session_context_registry
            or tool_factory.session_context_registry
        )
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
            self._session_context_registry.unregister(existing.session_id)
            logger.info("Evicted route=%s reason=broken", route_id)
            existing = None

        if existing and existing.needs_rebuild:
            await existing.destroy()
            self._sessions.pop(route_id, None)
            self._session_context_registry.unregister(existing.session_id)
            logger.info("Evicted route=%s reason=custom_prompt", route_id)
            existing = None

        if existing:
            return existing

        config = self._configs.get(chatbot_name)
        if config is None:
            raise ValueError(f"Chatbot '{chatbot_name}' not found")

        # Runtime anchor for the chatbot session on this route/chatbot pair.
        sdk_session_id = build_sdk_session_id(route_id, chatbot_name)

        # Resolve working directory: config.workdir or default per-session
        workdir = self._resolve_workdir(config.workdir, sdk_session_id)

        system_message = await self._build_system_message(
            config.system_message, route_id, workdir
        )
        model = self._route_model_overrides.get(route_id, config.model)
        tools = self._tool_factory.get_tools_for_chatbot(config.tools)
        tool_names = [t.name for t in tools] if tools else []
        logger.info(
            "Session setup route=%s chatbot=%s tools=%s workdir=%s",
            route_id, chatbot_name, tool_names, workdir,
        )

        # Try resume (preserves conversation history for same chatbot)
        try:
            sdk_session = await self._sdk.resume_session(
                session_id=sdk_session_id,
                model=model,
                system_message=system_message,
                tools=tools or None,
                working_directory=workdir,
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
                working_directory=workdir,
            )
            logger.info(
                "Created route=%s chatbot=%s", route_id, chatbot_name
            )

        session = ChatbotSession(sdk_session, config)
        self._sessions[route_id] = session
        platform, conversation_id = split_route_id(route_id)
        # Persist chatbot sessions as known-route metadata for admin views.
        self._session_context_registry.register(
            SessionContext(
                sdk_session_id=sdk_session_id,
                route_id=route_id,
                platform=platform,
                conversation_id=conversation_id,
                chatbot_name=chatbot_name,
            ),
            workdir=workdir,
        )
        return session

    @staticmethod
    def _resolve_workdir(
        config_workdir: str | None, session_id: str
    ) -> str:
        """Resolve workspace directory: config value or default per-session."""
        if config_workdir:
            path = Path(config_workdir)
        else:
            path = Path(DEFAULT_WORKSPACE_ROOT) / session_id
        path.mkdir(parents=True, exist_ok=True)
        return str(path.resolve())

    async def _build_system_message(
        self, base: str, route_id: str, workdir: str | None = None
    ) -> str:
        from chatpilot.core.time_service import TimeService

        parts = [base]

        # Time hint (dynamic from config timezone)
        parts.append(f"\n{TimeService.get().system_prompt_hint()}")

        # Workspace info
        if workdir:
            parts.append(
                f"\n[工作目錄]\n你的工作目錄是 {workdir}，"
                "如果需要暫存或輸出檔案，請放在這個目錄下。"
            )

        # Custom prompts
        if self._memory_store is not None:
            try:
                prompts = await self._memory_store.list(
                    route_id, "custom_prompt"
                )
            except Exception:
                prompts = []
            lines = [p["text"] for p in prompts if p.get("text")]
            if lines:
                custom_section = "\n- ".join(lines)
                parts.append(f"\n[使用者偏好]\n- {custom_section}")

        return "".join(parts)

    async def switch_chatbot(
        self, route_id: str, chatbot_name: str
    ) -> None:
        """Switch chatbot for a route. Destroys old session, creates fresh."""
        old = self._sessions.pop(route_id, None)
        if old:
            self._session_context_registry.unregister(old.session_id)
            await old.destroy()
        self._route_chatbot_overrides[route_id] = chatbot_name
        logger.info(
            "Switched chatbot route=%s to %s", route_id, chatbot_name
        )

    async def switch_model(self, route_id: str, new_model: str) -> None:
        """Switch model. Destroys session, next message resumes with new model."""
        old = self._sessions.pop(route_id, None)
        if old:
            self._session_context_registry.unregister(old.session_id)
            await old.destroy()
        self._route_model_overrides[route_id] = new_model
        logger.info("Switched model route=%s to %s", route_id, new_model)

    async def destroy_session(self, route_id: str) -> None:
        session = self._sessions.pop(route_id, None)
        if session:
            self._session_context_registry.unregister(session.session_id)
            await session.destroy()

    async def destroy_all(self) -> None:
        for route_id in list(self._sessions):
            await self.destroy_session(route_id)
