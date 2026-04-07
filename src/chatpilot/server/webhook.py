"""Webhook handler — thin route layer for POST /webhook/{platform}."""

from __future__ import annotations

import asyncio
import json as _json
import logging
import time
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from chatpilot.core.errors import AdapterError
from chatpilot.core.types import DiscoveryEvent, Message, Response
from chatpilot.routing.binding import NO_MATCH, calculate_score
from chatpilot.routing.onboarding import materialize_onboarding_state
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


def _load_route_labels() -> dict:
    labels_path = Path("data/route_labels.json")
    if not labels_path.exists():
        return {}
    return _json.loads(labels_path.read_text(encoding="utf-8"))


def _write_route_labels(labels: dict) -> None:
    labels_path = Path("data/route_labels.json")
    labels_path.parent.mkdir(parents=True, exist_ok=True)
    labels_path.write_text(
        _json.dumps(labels, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _resolve_route_label(adapter: object, conversation_id: str) -> str | None:
    get_label = getattr(adapter, "get_route_label", None)
    if callable(get_label):
        return get_label(conversation_id)

    api = getattr(adapter, "_api", None)
    if api is None:
        return None
    try:
        if conversation_id.startswith("C"):
            summary = api.get_group_summary(conversation_id)
            count_resp = api.get_group_member_count(conversation_id)
            count = getattr(count_resp, "count", count_resp)
            return f"{summary.group_name}（{count}人）"
        if conversation_id.startswith("U"):
            profile = api.get_profile(conversation_id)
            return f"{profile.display_name}（私訊）"
    except Exception:
        logger.exception("LINE label sync failed for %s", conversation_id)
    return None


def _resolve_static_binding(binding_router, info: dict) -> str | None:
    """Resolve the best static binding for an admin route view.

    This intentionally ignores discovery onboarding state and only evaluates the
    configured binding rules against a synthetic message for the route.
    """
    bindings = getattr(binding_router, "_bindings", None)
    weights = getattr(binding_router, "_weights", None)
    if bindings is None or weights is None:
        return None

    conversation_id = info["conversation_id"]
    route_type = "user" if conversation_id.startswith("U") else "group"
    message = Message(
        text="[admin route view]",
        user_id="admin-view" if route_type == "group" else conversation_id,
        user_name="",
        platform=info["platform"],
        group_id=conversation_id if route_type == "group" else None,
        conversation_id=conversation_id,
    )

    best_binding = None
    best_score = NO_MATCH
    for binding in bindings:
        score = calculate_score(binding, message, weights)
        if score == NO_MATCH:
            continue
        if score >= best_score:
            best_score = score
            best_binding = binding
    return best_binding.chatbot if best_binding is not None else None


def _apply_discovery_event(
    request: Request,
    adapter: object,
    event: DiscoveryEvent,
) -> None:
    config = request.app.state.config
    route_binding_service = request.app.state.route_binding_service
    refresh_runtime = request.app.state.refresh_routing_runtime
    label = _resolve_route_label(adapter, event.conversation_id)
    state = materialize_onboarding_state(config, event, label=label)
    if state is None:
        logger.info(
            "[discovery] no onboarding profile matched route=%s type=%s",
            event.route_id,
            event.discovery_type,
        )
        return

    entry = route_binding_service.upsert_from_onboarding(state)
    route_binding_service.save()
    refresh_runtime()
    if label:
        labels = _load_route_labels()
        labels[state.route_id] = label
        _write_route_labels(labels)
    logger.info(
        "[discovery] route=%s type=%s profile=%s chatbot=%s reply=%s processing=%s",
        state.route_id,
        state.discovery_type,
        entry.profile_name,
        entry.chatbot,
        entry.reply_policy,
        entry.processing_policy,
    )


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
                    if getattr(candidate, "platform", "") == "line":
                        logger.error(
                            "Legacy unnamed LINE adapter selected for webhook dispatch. "
                            "Expected named adapter key such as line:webric."
                        )
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

    parse_discovery = getattr(adapter, "parse_discovery_events", None)
    if callable(parse_discovery):
        discovery_events = await parse_discovery(request)
        for event in discovery_events:
            _apply_discovery_event(request, adapter, event)

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
    """List known routes for admin views.

    This endpoint reflects persisted/known route metadata, not a live list of
    currently running SDK sessions. `sessions` therefore means chatbots seen or
    persisted for that route, not active runtime actors.
    """
    chatbot_manager = request.app.state.chatbot_manager
    binding_router = request.app.state.binding_router
    route_binding_service = request.app.state.route_binding_service

    # Load labels
    labels: dict = _load_route_labels()

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
    for route_id, entry in route_binding_service.list_entries():
        conversation_id = route_id.rsplit(":", 1)[-1]
        platform = route_id[: -(len(conversation_id) + 1)]
        info = known_routes.setdefault(
            route_id,
            {
                "route_id": route_id,
                "platform": platform,
                "conversation_id": conversation_id,
                "sessions": [],
            },
        )
        info["binding_entry"] = entry
        info.setdefault("platform", platform)
        info.setdefault("conversation_id", conversation_id)

    # Enrich known-route metadata with current binding/override state.
    routes = []
    for route_id, info in sorted(known_routes.items()):
        exact_entry = info.get("binding_entry")
        override = chatbot_manager.get_current_chatbot(route_id)
        active_session = None
        get_session = getattr(chatbot_manager, "get_session", None)
        if get_session is not None:
            active_session = get_session(route_id)
        default_binding = _resolve_static_binding(binding_router, info)

        current_chatbot = (
            override
            or getattr(exact_entry, "chatbot", None)
            or getattr(active_session, "chatbot_name", None)
            or default_binding
        )
        if current_chatbot is None:
            current_chatbot = info["sessions"][0] if info["sessions"] else "unknown"
        configured_model = None
        effective_model = None
        if hasattr(chatbot_manager, "get_configured_model"):
            configured_model = chatbot_manager.get_configured_model(
                current_chatbot
            )
        if hasattr(chatbot_manager, "get_effective_model"):
            effective_model = chatbot_manager.get_effective_model(
                route_id, current_chatbot
            )
        session_model = getattr(active_session, "model", None)
        sdk_current_model = None
        if active_session is not None:
            get_runtime_model = getattr(active_session, "get_runtime_model", None)
            if get_runtime_model is not None:
                sdk_current_model = await get_runtime_model()

        item = {
            "route_id": route_id,
            "label": labels.get(route_id),
            "platform": info["platform"],
            "conversation_id": info["conversation_id"],
            "current_chatbot": current_chatbot,
            "override": override,
            "default_binding": default_binding,
            "configured_model": configured_model,
            "effective_model": effective_model,
            "session_model": session_model,
            "sdk_current_model": sdk_current_model,
            "sessions": sorted(set(info["sessions"])),
        }
        if exact_entry is not None:
            item["binding_source"] = exact_entry.source
            item["reply_policy"] = exact_entry.reply_policy
            item["processing_policy"] = exact_entry.processing_policy
            if exact_entry.profile_name is not None:
                item["discovered_profile"] = exact_entry.profile_name
        routes.append(item)

    return JSONResponse(content={"routes": routes, "total": len(routes)})


@router.post("/cli/routes/label")
async def cli_route_label(request: Request) -> JSONResponse:
    """Set a label for a route_id."""
    body = await request.json()
    route_id = body.get("route_id", "")
    label = body.get("label", "")

    if not route_id:
        return JSONResponse(status_code=400, content={"error": "route_id required"})

    labels: dict = _load_route_labels()

    if label:
        labels[route_id] = label
    else:
        labels.pop(route_id, None)

    _write_route_labels(labels)
    return JSONResponse(content={"route_id": route_id, "label": label or None})


@router.post("/cli/routes/sync")
async def cli_routes_sync(request: Request) -> JSONResponse:
    """Sync route labels from platform APIs (LINE group names, user profiles)."""
    adapters: dict = request.app.state.adapters
    synced: list[dict] = []
    route_binding_service = request.app.state.route_binding_service

    # LINE: query group summary / profile for known conversations
    seen: set[str] = set()
    route_records: list[tuple[str, str, str]] = []
    for context in _load_known_session_contexts(request):
        route_records.append((
            context.route_id,
            context.platform,
            context.conversation_id,
        ))
    for route_id, _entry in route_binding_service.list_entries():
        conversation_id = route_id.rsplit(":", 1)[-1]
        platform = route_id[: -(len(conversation_id) + 1)]
        route_records.append((route_id, platform, conversation_id))
    for route_id, route_platform, conversation_id in route_records:
        if not route_platform.startswith("line"):
            continue
        if route_id in seen:
            continue
        seen.add(route_id)
        line_adapter = adapters.get(route_platform)
        if line_adapter is None:
            continue
        label = _resolve_route_label(line_adapter, conversation_id)
        if label:
            synced.append({
                "route_id": route_id,
                "label": label,
            })

    # Write labels
    if synced:
        labels: dict = _load_route_labels()
        for item in synced:
            labels[item["route_id"]] = item["label"]
        _write_route_labels(labels)

    return JSONResponse(content={"synced": synced, "total": len(synced)})


@router.post("/cli/reload")
async def cli_reload(request: Request) -> JSONResponse:
    """Force reload config from disk."""
    reload_config = getattr(request.app.state, "reload_config", None)
    if callable(reload_config):
        reload_config()
        return JSONResponse(content={"status": "reloaded"})
    return JSONResponse(status_code=500, content={"error": "reload unavailable"})


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
