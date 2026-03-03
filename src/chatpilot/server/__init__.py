"""FastAPI application factory and startup lifecycle."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI

from chatpilot.agents import agent_registry, register_agent
from chatpilot.agents.general import general_agent
from chatpilot.agents.warehouse import warehouse_agent
from chatpilot.channels.adapter import AdapterRegistry
from chatpilot.channels.line import line_adapter
from chatpilot.channels.mock import mock_adapter
from chatpilot.core.errors import RouteError
from chatpilot.dispatch.route_loader import RouteWatcher, load_routes
from chatpilot.sdk.session_manager import session_manager
from chatpilot.server.webhook import router

logger = logging.getLogger(__name__)

_route_watcher: RouteWatcher | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle."""
    global _route_watcher

    # Load .env
    load_dotenv()

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    # Start Copilot SDK
    await session_manager.start()

    # Register adapters
    adapter_registry: AdapterRegistry = {}
    line_adapter.initialize()
    adapter_registry["line"] = line_adapter
    adapter_registry["mock"] = mock_adapter
    app.state.adapter_registry = adapter_registry

    # Register agents
    register_agent(general_agent)
    register_agent(warehouse_agent)

    # Load routes
    routes_path = os.environ.get("ROUTES_PATH", "config/routes.yaml")
    try:
        route_map = load_routes(routes_path)
        app.state.route_map = route_map
        logger.info(
            "Route map loaded: %d route(s) from %s", len(route_map.routes), routes_path
        )

        # Validate agent names in routes
        for rule in route_map.routes:
            for kw in rule.keywords:
                if kw.agent_name not in agent_registry:
                    raise RouteError(f"unknown agent in routes: {kw.agent_name}")
            if rule.fallback_agent and rule.fallback_agent not in agent_registry:
                raise RouteError(f"unknown agent in routes: {rule.fallback_agent}")
    except FileNotFoundError:
        from chatpilot.core.types import RouteMap

        logger.warning(
            "Routes file not found: %s — starting with empty routes", routes_path
        )
        app.state.route_map = RouteMap(routes=[])

    # Store routes_path for /model command write-back
    app.state.routes_path = routes_path

    # Timeout config
    app.state.reply_timeout_ms = int(os.environ.get("REPLY_TIMEOUT_MS", "20000"))

    # Push API flag (no-op for MVP)
    app.state.push_api_enabled = (
        os.environ.get("PUSH_API_ENABLED", "false").lower() == "true"
    )

    # Start route watcher
    def on_route_change(new_map):
        app.state.route_map = new_map

    try:
        _route_watcher = RouteWatcher(
            routes_path,
            on_change=on_route_change,
            agent_registry=agent_registry,
        )
        _route_watcher.start()
    except Exception as e:
        logger.warning("Could not start RouteWatcher: %s", e)

    logger.info("Server started. Webhook endpoint: POST /webhook/{platform}")

    yield

    # Shutdown
    if _route_watcher is not None:
        _route_watcher.stop()
    await session_manager.stop()
    logger.info("[SHUTDOWN] server stopped")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(title="ChatPilot Agent Gateway", lifespan=lifespan)
    app.include_router(router)
    return app


app = create_app()
