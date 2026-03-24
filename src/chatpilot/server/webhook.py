"""Webhook handler — thin route layer for POST /webhook/{platform}."""

from __future__ import annotations

import asyncio
import logging
import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from chatpilot.core.types import Message, Response

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/webhook/{platform}")
async def webhook_handler(platform: str, request: Request) -> JSONResponse:
    """Handle incoming webhook from any platform."""
    adapters: dict = request.app.state.adapters
    hub = request.app.state.hub

    adapter = adapters.get(platform)
    if adapter is None:
        return JSONResponse(
            status_code=404,
            content={"error": f"Unknown platform: {platform}", "code": "PLATFORM_UNKNOWN"},
        )

    try:
        await adapter.verify_request(request)
    except Exception as e:
        logger.warning("Signature verification failed for %s: %s", platform, e)
        return JSONResponse(
            status_code=401,
            content={"error": "Invalid signature", "code": "SIGNATURE_INVALID"},
        )

    messages = await adapter.parse_messages(request)
    for msg in messages:
        await hub.receive(msg, adapter)

    return JSONResponse(status_code=200, content={"status": "ok"})


@router.post("/cli/chat")
async def cli_chat(request: Request) -> JSONResponse:
    """Synchronous chat endpoint for CLI testing.

    Goes through the full flow (hub → router → chatbot → SDK)
    but waits for the response and returns it.
    """
    hub = request.app.state.hub
    body = await request.json()

    text = body.get("message", body.get("text", ""))
    user_id = body.get("user_id", "cli-user")
    if not text:
        return JSONResponse(
            status_code=400,
            content={"error": "message is required"},
        )

    # Create a response capture adapter
    response_event = asyncio.Event()
    captured: dict = {"text": ""}

    class _CliCaptureAdapter:
        """Temporary adapter that captures the response."""

        @property
        def platform(self) -> str:
            return "cli"

        @property
        def format_hint(self) -> str | None:
            return None

        async def send_reply(self, message: Message, response: Response) -> None:
            captured["text"] = response.text
            response_event.set()

        async def push_message(self, route_id: str, response: Response) -> None:
            captured["text"] = response.text
            response_event.set()

        async def download_media(self, media_id: str) -> bytes | None:
            return None

    adapter = _CliCaptureAdapter()
    msg = Message(
        text=text,
        user_id=user_id,
        platform="cli",
        conversation_id=user_id,
        is_mention=True,
    )

    await hub.receive(msg, adapter)
    try:
        await asyncio.wait_for(response_event.wait(), timeout=300)
    except asyncio.TimeoutError:
        return JSONResponse(
            status_code=504,
            content={"error": "Chatbot timeout"},
        )

    return JSONResponse(content={"response": captured["text"]})


@router.get("/cli/routes")
async def cli_routes(request: Request) -> JSONResponse:
    """List all known routes with chatbot binding info."""
    from pathlib import Path

    chatbot_manager = request.app.state.chatbot_manager
    binding_router = request.app.state.binding_router

    # Collect route_ids from SDK session state
    session_dir = Path.home() / ".copilot" / "session-state"
    known_routes: dict[str, dict] = {}

    if session_dir.exists():
        for entry in session_dir.iterdir():
            name = entry.name
            # Our session IDs: {platform}-{conversation_id}__{chatbot}
            if "__" not in name:
                continue
            route_part, chatbot = name.rsplit("__", 1)
            # Reconstruct route_id: first - → :
            route_id = route_part.replace("-", ":", 1)
            if route_id not in known_routes:
                known_routes[route_id] = {
                    "route_id": route_id,
                    "platform": route_id.split(":")[0],
                    "conversation_id": route_id.split(":", 1)[1],
                    "sessions": [],
                }
            known_routes[route_id]["sessions"].append(chatbot)

    # Enrich with current state
    routes = []
    for route_id, info in sorted(known_routes.items()):
        override = chatbot_manager.get_current_chatbot(route_id)
        # Find default binding
        default_binding = None
        for b in binding_router._bindings:
            match = b.match
            if not match:
                default_binding = b.chatbot
            elif match.get("platform") == info["platform"]:
                default_binding = b.chatbot
            if match.get("group_id") == info["conversation_id"]:
                default_binding = b.chatbot
                break

        routes.append({
            "route_id": route_id,
            "platform": info["platform"],
            "conversation_id": info["conversation_id"],
            "current_chatbot": override or default_binding or "unknown",
            "override": override,
            "default_binding": default_binding,
            "sessions": sorted(set(info["sessions"])),
        })

    return JSONResponse(content={"routes": routes, "total": len(routes)})


@router.post("/cli/reload")
async def cli_reload(request: Request) -> JSONResponse:
    """Force reload config from routes.yaml."""
    import os
    config_path = request.app.state.config_path
    os.utime(config_path)  # touch to trigger watchdog
    return JSONResponse(content={"status": "reloaded"})


@router.get("/health")
async def health(request: Request) -> JSONResponse:
    """Health check endpoint."""
    uptime = time.time() - request.app.state.start_time
    return JSONResponse(
        content={
            "status": "ok",
            "version": "0.2.0",
            "uptime_seconds": int(uptime),
        }
    )
