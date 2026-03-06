"""MessageProcessor — platform-agnostic message processing pipeline."""

from __future__ import annotations

import asyncio
import logging
import time

from chatpilot.channels.adapter import ChannelAdapter
from chatpilot.core.types import Message, Response, RouteConfig
from chatpilot.processing.command_handler import CommandHandler
from chatpilot.queue.pending_queue import pending_queue
from chatpilot.sdk.session_manager import SessionManager
from chatpilot.server.session_gate import session_gate

logger = logging.getLogger(__name__)


def _log(conversation_id: str | None, category: str, detail: str) -> None:
    ts = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
    cid = conversation_id or "private"
    print(f"[{ts}] [{cid}] {category} {detail}", flush=True)


class MessageProcessor:
    """Platform-agnostic message processing pipeline.

    Pipeline: command check → gate → resolve route → agent handle → respond
    """

    def __init__(
        self,
        route_config: RouteConfig,
        routes_path: str,
        agents: dict,
        timeout_s: float = 20.0,
    ) -> None:
        self.route_config = route_config
        self.routes_path = routes_path
        self.agents = agents
        self.timeout_s = timeout_s
        self.command_handler = CommandHandler()

    async def process(self, msg: Message, adapter: ChannelAdapter) -> None:
        # Bail out early if platform is not registered
        if msg.platform not in self.route_config.platforms:
            _log(msg.conversation_id, "SKIP", f"unregistered platform={msg.platform}")
            return

        session_id = SessionManager.get_session_id(
            msg.platform, msg.conversation_id, msg.user_id
        )

        _log(msg.conversation_id, "RECV", f'platform={msg.platform} text="{msg.text}"')

        # 1. Commands — instant, no gate
        reply = self.command_handler.try_handle(
            msg, self.route_config, self.routes_path
        )
        if reply is not None:
            _log(msg.conversation_id, "CMD", f'"{reply[:80]}"')
            await adapter.send_response(msg, Response(text=reply))
            return

        # 2. Gate check
        if session_gate.is_busy(session_id):
            session_gate.queue(session_id, msg.text)
            _log(msg.conversation_id, "GATE", "session busy, queued message")
            await adapter.send_response(msg, Response(text="目前正在處理中，請稍候…"))
            return

        session_gate.acquire(session_id)
        bg = False
        try:
            bg = await self._handle_with_agent(msg, adapter, session_id)
        except Exception:
            bg = False
            raise
        finally:
            if not bg:
                self._release_gate(session_id)

    async def _handle_with_agent(
        self,
        msg: Message,
        adapter: ChannelAdapter,
        session_id: str,
    ) -> bool:
        """Resolve route, handle with agent. Returns True if background task spawned."""
        agent_name, model, workdir = self._resolve_route(msg)
        agent = self.agents.get(agent_name)

        if agent is None:
            _log(msg.conversation_id, "ROUTE", f"agent not found: {agent_name}")
            return False

        _log(msg.conversation_id, "ROUTE", f"agent={agent_name} model={model}")

        # Collect pending messages
        pending_texts = self._collect_pending(session_id)

        try:
            response = await asyncio.wait_for(
                agent.handle(msg, session_id, model=model, workdir=workdir),
                timeout=self.timeout_s,
            )
            _log(
                msg.conversation_id,
                "AGENT",
                f'agent={agent_name} text="{response.text[:100]}"',
            )
            reply_text = self._combine_pending(pending_texts, response.text)
            await adapter.send_response(msg, Response(text=reply_text))
            return False
        except asyncio.TimeoutError:
            _log(msg.conversation_id, "TIMEOUT", f"agent={agent_name}")
            for text in pending_texts:
                pending_queue.enqueue(session_id, text)
            await adapter.send_processing_ack(msg)
            asyncio.create_task(
                self._background_handle(msg, agent, session_id, model=model)
            )
            return True
        except Exception as e:
            _log(msg.conversation_id, "ERROR", f"agent={agent_name} error={e}")
            error_text = "抱歉，處理時發生錯誤，請稍後再試。"
            if pending_texts:
                error_text = "\n\n".join(pending_texts) + "\n\n" + error_text
            await adapter.send_response(msg, Response(text=error_text))
            return False

    def _resolve_route(
        self, msg: Message
    ) -> tuple[str, str | None, str | None]:
        """Look up agent, model, workdir for a message."""
        platform_config = self.route_config.platforms.get(msg.platform)
        if not platform_config:
            return "general-agent", None, None
        key = msg.conversation_id or "null"
        route = platform_config.conversation_routes.get(key)
        if not route:
            return platform_config.default_agent, None, None
        return route.agent, route.model, route.workdir

    def _collect_pending(self, session_id: str) -> list[str]:
        texts: list[str] = []
        pending = pending_queue.dequeue(session_id)
        while pending is not None:
            texts.append(pending.content)
            pending = pending_queue.dequeue(session_id)
        return texts

    def _combine_pending(self, pending_texts: list[str], response_text: str) -> str:
        if pending_texts:
            return "\n\n".join(pending_texts) + "\n\n" + response_text
        return response_text

    def _release_gate(self, session_id: str) -> None:
        dropped = session_gate.release(session_id)
        if dropped:
            pending_queue.enqueue(
                session_id,
                f"（您稍早傳送的訊息「{dropped[:30]}」已略過，請重新發送）",
            )

    async def _background_handle(
        self, msg: Message, agent, session_id: str, model: str | None = None
    ) -> None:
        try:
            response = await agent.handle(msg, session_id, model=model)
            pending_queue.enqueue(session_id, response.text)
            _log(
                msg.conversation_id,
                "QUEUED",
                f'agent={agent.name} text="{response.text[:50]}..."',
            )
        except Exception as e:
            _log(msg.conversation_id, "ERROR", f"background handle failed: {e}")
        finally:
            self._release_gate(session_id)
