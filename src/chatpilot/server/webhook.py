"""Webhook handler — thin route layer for POST /webhook/{platform}."""

from __future__ import annotations

import asyncio
import logging
import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from chatpilot.core.errors import AdapterError
from chatpilot.core.types import Message, Response
from chatpilot.tools.session_context import (
    DEFAULT_WORKSPACE_ROOT,
    SessionContextRegistry,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _line_adapter_candidates(adapters: dict) -> list:
    named = [
        adapter
        for key, adapter in adapters.items()
        if key.startswith("line:")
    ]
    fallback = [adapters["line"]] if "line" in adapters else []
    return named + fallback


def _load_known_session_contexts(request: Request) -> list:
    registry = getattr(request.app.state, "session_context_registry", None)
    if registry is None:
        registry = SessionContextRegistry()

    known = {
        context.sdk_session_id: context
        for context in registry.list_contexts()
    }
    for context in registry.scan_workspace_sidecars(DEFAULT_WORKSPACE_ROOT):
        known.setdefault(context.sdk_session_id, context)
    return list(known.values())


@router.post("/webhook/{platform}")
async def webhook_handler(platform: str, request: Request) -> JSONResponse:
    """Handle incoming webhook from any platform."""
    adapters: dict = request.app.state.adapters
    hub = request.app.state.hub

    adapter = adapters.get(platform)
    if platform == "line":
        candidates = _line_adapter_candidates(adapters)
        if candidates:
            adapter = None
            for candidate in candidates:
                try:
                    await candidate.verify_request(request)
                    adapter = candidate
                    break
                except AdapterError:
                    continue
                except Exception:
                    logger.exception(
                        "Unexpected LINE verification failure for %s",
                        getattr(candidate, "platform", "?"),
                    )
                    return JSONResponse(
                        status_code=500,
                        content={"error": "LINE verification failed"},
                    )
            if adapter is None:
                logger.warning("Signature verification failed for %s", platform)
                return JSONResponse(
                    status_code=401,
                    content={"error": "Invalid signature", "code": "SIGNATURE_INVALID"},
                )

    if adapter is None:
        return JSONResponse(
            status_code=404,
            content={"error": f"Unknown platform: {platform}", "code": "PLATFORM_UNKNOWN"},
        )

    if platform != "line":
        try:
            await adapter.verify_request(request)
        except AdapterError as e:
            logger.warning("Signature verification failed for %s: %s", platform, e)
            return JSONResponse(
                status_code=401,
                content={"error": "Invalid signature", "code": "SIGNATURE_INVALID"},
            )
        except Exception:
            logger.exception("Unexpected verification failure for %s", platform)
            return JSONResponse(
                status_code=500,
                content={"error": "Verification failed"},
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
    group_id = body.get("group_id")
    if not text:
        return JSONResponse(
            status_code=400,
            content={"error": "message is required"},
        )

    # Create a response capture adapter
    response_event = asyncio.Event()
    captured: dict = {"text": ""}

    platform_name = body.get("platform", "cli")

    class _CliCaptureAdapter:
        """Temporary adapter that captures the response."""

        @property
        def platform(self) -> str:
            return platform_name

        @property
        def format_hint(self) -> str | None:
            if platform_name == "line":
                return (
                    "[格式限制] 此平台不支援 Markdown。"
                    "不要使用 **粗體**、`程式碼`、## 標題、[連結](url)。"
                    "用純文字和換行來排版。"
                )
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
    conv_id = group_id or user_id
    msg = Message(
        text=text,
        user_id=user_id,
        group_id=group_id,
        platform="cli",
        conversation_id=conv_id,
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
    import json as _json
    from pathlib import Path

    chatbot_manager = request.app.state.chatbot_manager
    binding_router = request.app.state.binding_router

    # Load labels
    labels_path = Path("data/route_labels.json")
    labels: dict = {}
    if labels_path.exists():
        labels = _json.loads(labels_path.read_text(encoding="utf-8"))

    known_routes: dict[str, dict] = {}
    for context in _load_known_session_contexts(request):
        route_id = context.route_id
        if route_id not in known_routes:
            known_routes[route_id] = {
                "route_id": route_id,
                "platform": context.platform,
                "conversation_id": context.conversation_id,
                "sessions": [],
            }
        known_routes[route_id]["sessions"].append(context.chatbot_name)

    # Enrich with current state
    routes = []
    for route_id, info in sorted(known_routes.items()):
        override = chatbot_manager.get_current_chatbot(route_id)
        # Find default binding (check all match dimensions)
        default_binding = None
        for b in binding_router._bindings:
            match = b.match
            if not match:
                default_binding = default_binding or b.chatbot
                continue
            cid = info["conversation_id"]
            if match.get("group_id") == cid:
                default_binding = b.chatbot
                break
            if match.get("user_id") == cid:
                default_binding = b.chatbot
                break
            if match.get("platform") == info["platform"] and not default_binding:
                default_binding = b.chatbot

        routes.append({
            "route_id": route_id,
            "label": labels.get(route_id),
            "platform": info["platform"],
            "conversation_id": info["conversation_id"],
            "current_chatbot": (
                override
                or default_binding
                or (info["sessions"][0] if info["sessions"] else "unknown")
            ),
            "override": override,
            "default_binding": default_binding,
            "sessions": sorted(set(info["sessions"])),
        })

    return JSONResponse(content={"routes": routes, "total": len(routes)})


@router.post("/cli/routes/label")
async def cli_route_label(request: Request) -> JSONResponse:
    """Set a label for a route_id."""
    import json
    from pathlib import Path

    body = await request.json()
    route_id = body.get("route_id", "")
    label = body.get("label", "")

    if not route_id:
        return JSONResponse(status_code=400, content={"error": "route_id required"})

    labels_path = Path("data/route_labels.json")
    labels_path.parent.mkdir(parents=True, exist_ok=True)
    labels: dict = {}
    if labels_path.exists():
        labels = json.loads(labels_path.read_text(encoding="utf-8"))

    if label:
        labels[route_id] = label
    else:
        labels.pop(route_id, None)

    labels_path.write_text(
        json.dumps(labels, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return JSONResponse(content={"route_id": route_id, "label": label or None})


@router.post("/cli/routes/sync")
async def cli_routes_sync(request: Request) -> JSONResponse:
    """Sync route labels from platform APIs (LINE group names, etc.)."""
    from pathlib import Path

    adapters: dict = request.app.state.adapters
    synced: list[dict] = []

    # LINE: query group summary for group conversations
    seen: set[str] = set()
    for context in _load_known_session_contexts(request):
        if not context.platform.startswith("line"):
            continue
        if not context.conversation_id.startswith("C"):
            continue
        if context.route_id in seen:
            continue
        seen.add(context.route_id)
        line_adapter = adapters.get(context.platform)
        if line_adapter is None:
            continue
        try:
            summary = line_adapter._api.get_group_summary(context.conversation_id)
            count_resp = line_adapter._api.get_group_member_count(
                context.conversation_id
            )
            count = getattr(count_resp, "count", count_resp)
            label = f"{summary.group_name}（{count}人）"
            synced.append({
                "route_id": context.route_id,
                "label": label,
            })
        except Exception:
            logger.exception("LINE sync failed for %s", context.route_id)

    # Write labels
    if synced:
        import json as _json

        labels_path = Path("data/route_labels.json")
        labels_path.parent.mkdir(parents=True, exist_ok=True)
        labels: dict = {}
        if labels_path.exists():
            labels = _json.loads(labels_path.read_text(encoding="utf-8"))
        for item in synced:
            labels[item["route_id"]] = item["label"]
        labels_path.write_text(
            _json.dumps(labels, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    return JSONResponse(content={"synced": synced, "total": len(synced)})


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
