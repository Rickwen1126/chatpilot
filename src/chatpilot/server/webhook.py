"""Webhook handler — POST /webhook/{platform} route."""

from __future__ import annotations

import asyncio
import logging
import sys
import time

from fastapi import APIRouter, Request, Response

from chatpilot.agents import agent_registry
from chatpilot.channels.adapter import AdapterRegistry
from chatpilot.core.errors import AgentError
from chatpilot.core.types import (
    FallbackMatch,
    Ignored,
    KeywordMatch,
    Message,
    RouteMap,
)
from chatpilot.dispatch.dispatcher import dispatch
from chatpilot.queue.pending_queue import pending_queue
from chatpilot.sdk.session_manager import SessionManager

logger = logging.getLogger(__name__)

router = APIRouter()


def _log(conversation_id: str | None, category: str, detail: str) -> None:
    """Structured log to stdout per FR-014."""
    ts = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
    cid = conversation_id or "private"
    print(f"[{ts}] [{cid}] {category} {detail}", flush=True)


@router.post("/webhook/{platform}")
async def webhook_handler(platform: str, request: Request) -> Response:
    """Handle incoming webhook from any platform."""
    app = request.app
    adapter_registry: AdapterRegistry = app.state.adapter_registry
    route_map: RouteMap = app.state.route_map
    reply_timeout_ms: int = app.state.reply_timeout_ms

    # 1. Look up adapter
    adapter = adapter_registry.get(platform)
    if adapter is None:
        return Response(status_code=400, content=f"Unknown platform: {platform}")

    # 2. Read raw body
    raw_body = await request.body()

    # 3. Verify signature
    signature = request.headers.get("x-line-signature", "")
    if not adapter.verify_signature(raw_body, signature):
        return Response(status_code=401, content="Invalid signature")

    # 4. Parse messages
    if hasattr(adapter, "parse_messages_with_signature"):
        messages = adapter.parse_messages_with_signature(raw_body, signature)
    else:
        messages = adapter.parse_messages(raw_body)

    # 5. Process each message
    for msg in messages:
        await _process_message(msg, adapter, route_map, reply_timeout_ms)

    return Response(status_code=200, content="OK")


async def _process_message(
    msg: Message,
    adapter,
    route_map: RouteMap,
    reply_timeout_ms: int,
) -> None:
    """Process a single message: dequeue pending, dispatch, handle, respond."""
    session_id = SessionManager.get_session_id(
        msg.platform, msg.conversation_id, msg.user_id
    )

    _log(msg.conversation_id, "RECV", f'platform={msg.platform} text="{msg.text}"')

    # Dequeue and send any pending messages first
    pending = pending_queue.dequeue(session_id)
    while pending is not None:
        _log(
            msg.conversation_id,
            "PENDING",
            f'delivering deferred response: "{pending.content[:50]}..."',
        )
        try:
            from chatpilot.core.types import Response as Resp

            await adapter.send_response(msg, Resp(text=pending.content))
        except Exception as e:
            _log(msg.conversation_id, "ERROR", f"Failed to deliver pending: {e}")
        pending = pending_queue.dequeue(session_id)

    # Dispatch
    result, agent = dispatch(msg, route_map, agent_registry)

    if isinstance(result, KeywordMatch):
        _log(
            msg.conversation_id,
            "ROUTE",
            f'keyword="{result.keyword}" agent={result.agent_name}',
        )
    elif isinstance(result, FallbackMatch):
        _log(msg.conversation_id, "ROUTE", f"fallback agent={result.agent_name}")
    elif isinstance(result, Ignored):
        _log(msg.conversation_id, "ROUTE", f"ignored reason={result.reason}")
        return

    if agent is None:
        return

    # Handle with timeout
    timeout_s = reply_timeout_ms / 1000.0
    try:
        response = await asyncio.wait_for(
            agent.handle(msg, session_id),
            timeout=timeout_s,
        )
        _log(
            msg.conversation_id,
            "AGENT",
            f'agent={agent.name} text="{response.text[:100]}"',
        )
        await adapter.send_response(msg, response)
    except asyncio.TimeoutError:
        _log(
            msg.conversation_id,
            "TIMEOUT",
            f"agent={agent.name} timeout={reply_timeout_ms}ms",
        )
        await adapter.send_processing_ack(msg)
        # Continue agent processing in background and enqueue result
        asyncio.create_task(_background_handle(msg, agent, session_id))
    except AgentError as e:
        _log(msg.conversation_id, "ERROR", f"agent={agent.name} error={e}")
        from chatpilot.core.types import Response as Resp

        await adapter.send_response(
            msg, Resp(text="抱歉，處理時發生錯誤，請稍後再試。")
        )
    except Exception as e:
        _log(msg.conversation_id, "ERROR", f"unexpected: {e}")
        print(f"[ERROR] {e}", file=sys.stderr)
        from chatpilot.core.types import Response as Resp

        await adapter.send_response(msg, Resp(text="系統發生異常，請稍後再試。"))


async def _background_handle(msg: Message, agent, session_id: str) -> None:
    """Handle agent response in background after timeout, enqueue result."""
    try:
        response = await agent.handle(msg, session_id)
        pending_queue.enqueue(session_id, response.text)
        _log(
            msg.conversation_id,
            "QUEUED",
            f'agent={agent.name} text="{response.text[:50]}..."',
        )
    except Exception as e:
        _log(msg.conversation_id, "ERROR", f"background handle failed: {e}")
