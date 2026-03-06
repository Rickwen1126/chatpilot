"""Webhook handler — POST /webhook/{platform} route."""

from __future__ import annotations

import asyncio
import logging
import sys
import time

from fastapi import APIRouter, Request, Response

from chatpilot.agents import agent_registry, get_agent
from chatpilot.channels.adapter import AdapterRegistry
from chatpilot.commands.model_command import handle_model_command
from chatpilot.core.errors import AgentError
from chatpilot.core.types import (
    FallbackMatch,
    Ignored,
    KeywordMatch,
    Message,
    RouteMap,
)
from chatpilot.dispatch.dispatcher import _find_rule, dispatch
from chatpilot.queue.pending_queue import pending_queue
from chatpilot.sdk.session_manager import SessionManager
from chatpilot.server.session_gate import session_gate

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
    routes_path: str = getattr(app.state, "routes_path", "")

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
        await _process_message(msg, adapter, route_map, reply_timeout_ms, routes_path)

    return Response(status_code=200, content="OK")


async def _process_message(
    msg: Message,
    adapter,
    route_map: RouteMap,
    reply_timeout_ms: int,
    routes_path: str = "",
) -> None:
    """Process a single message: gate check, dequeue pending, dispatch, handle."""
    session_id = SessionManager.get_session_id(
        msg.platform, msg.conversation_id, msg.user_id
    )

    _log(msg.conversation_id, "RECV", f'platform={msg.platform} text="{msg.text}"')

    # /model is instant — no gate
    stripped = msg.text.strip()
    if stripped.lower().startswith("/model"):
        route_rule = _find_rule(msg, route_map)
        reply_text = handle_model_command(
            msg.text, route_rule, route_map, routes_path
        )
        from chatpilot.core.types import Response as Resp

        _log(msg.conversation_id, "CMD", f'/model → "{reply_text[:80]}"')
        await adapter.send_response(msg, Resp(text=reply_text))
        return

    # Session gate — block concurrent processing
    if session_gate.is_busy(session_id):
        session_gate.queue(session_id, msg.text)
        from chatpilot.core.types import Response as Resp

        _log(msg.conversation_id, "GATE", "session busy, queued message")
        await adapter.send_response(msg, Resp(text="目前正在處理中，請稍候…"))
        return

    session_gate.acquire(session_id)
    try:
        bg = await _do_process(msg, adapter, route_map, reply_timeout_ms, session_id)
    except Exception:
        bg = False
        raise
    finally:
        # If a background task was spawned, it owns the gate release
        if not bg:
            _release_gate(session_id)


def _release_gate(session_id: str) -> None:
    """Release session gate and enqueue drop notice if a message was queued."""
    dropped = session_gate.release(session_id)
    if dropped:
        pending_queue.enqueue(
            session_id,
            f"（您稍早傳送的訊息「{dropped[:30]}」已略過，請重新發送）",
        )


async def _do_process(
    msg: Message,
    adapter,
    route_map: RouteMap,
    reply_timeout_ms: int,
    session_id: str,
) -> bool:
    """Core processing: /倉管, dispatch, agent handle — called inside gate.

    Returns True if a background task was spawned (caller must NOT release gate).
    """
    stripped = msg.text.strip()

    if stripped.startswith("/倉管"):
        agent = get_agent("warehouse-agent")
        if agent is None:
            return False
        query = stripped[len("/倉管"):].strip() or "庫存"
        query_msg = msg.model_copy(update={"text": query})
        # Use model from route rule so /倉管 respects yaml config
        route_rule = _find_rule(msg, route_map)
        model = route_rule.model if route_rule else None
        timeout_s = reply_timeout_ms / 1000.0
        try:
            response = await asyncio.wait_for(
                agent.handle(query_msg, session_id, model=model),
                timeout=timeout_s,
            )
            _log(
                msg.conversation_id,
                "CMD",
                f'/倉管 model={model} → "{response.text[:80]}"',
            )
            await adapter.send_response(msg, response)
        except asyncio.TimeoutError:
            _log(
                msg.conversation_id,
                "TIMEOUT",
                f"/倉管 timeout={reply_timeout_ms}ms",
            )
            await adapter.send_processing_ack(msg)
            asyncio.create_task(
                _background_handle(msg, agent, session_id, model=model)
            )
            return True
        return False

    # Collect pending messages (don't send yet — reserve the reply token)
    pending_texts: list[str] = []
    pending = pending_queue.dequeue(session_id)
    while pending is not None:
        _log(
            msg.conversation_id,
            "PENDING",
            f'collected deferred response: "{pending.content[:50]}..."',
        )
        pending_texts.append(pending.content)
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
        # Still deliver pending even if dispatch is ignored
        if pending_texts:
            from chatpilot.core.types import Response as Resp

            await adapter.send_response(
                msg, Resp(text="\n\n".join(pending_texts))
            )
        return False

    if agent is None:
        if pending_texts:
            from chatpilot.core.types import Response as Resp

            await adapter.send_response(
                msg, Resp(text="\n\n".join(pending_texts))
            )
        return False

    # Extract model from dispatch result
    model = result.model if isinstance(result, (KeywordMatch, FallbackMatch)) else None

    # Handle with timeout
    timeout_s = reply_timeout_ms / 1000.0
    try:
        response = await asyncio.wait_for(
            agent.handle(msg, session_id, model=model),
            timeout=timeout_s,
        )
        _log(
            msg.conversation_id,
            "AGENT",
            f'agent={agent.name} model={model} text="{response.text[:100]}"',
        )
        # Combine pending + agent response into a single reply
        reply_text = response.text
        if pending_texts:
            reply_text = "\n\n".join(pending_texts) + "\n\n" + reply_text
        from chatpilot.core.types import Response as Resp

        await adapter.send_response(msg, Resp(text=reply_text))
    except asyncio.TimeoutError:
        _log(
            msg.conversation_id,
            "TIMEOUT",
            f"agent={agent.name} timeout={reply_timeout_ms}ms",
        )
        # Re-enqueue pending so they aren't lost
        for text in pending_texts:
            pending_queue.enqueue(session_id, text)
        await adapter.send_processing_ack(msg)
        # Continue agent processing in background and enqueue result
        asyncio.create_task(_background_handle(msg, agent, session_id, model=model))
        return True
    except AgentError as e:
        _log(msg.conversation_id, "ERROR", f"agent={agent.name} error={e}")
        from chatpilot.core.types import Response as Resp

        error_text = "抱歉，處理時發生錯誤，請稍後再試。"
        if pending_texts:
            error_text = "\n\n".join(pending_texts) + "\n\n" + error_text
        await adapter.send_response(msg, Resp(text=error_text))
    except Exception as e:
        _log(msg.conversation_id, "ERROR", f"unexpected: {e}")
        print(f"[ERROR] {e}", file=sys.stderr)
        from chatpilot.core.types import Response as Resp

        error_text = "系統發生異常，請稍後再試。"
        if pending_texts:
            error_text = "\n\n".join(pending_texts) + "\n\n" + error_text
        await adapter.send_response(msg, Resp(text=error_text))
    return False


async def _background_handle(
    msg: Message, agent, session_id: str, model: str | None = None
) -> None:
    """Handle agent response in background after timeout, enqueue result."""
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
        _release_gate(session_id)
