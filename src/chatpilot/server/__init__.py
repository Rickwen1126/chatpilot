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
from chatpilot.dispatch.route_loader import load_route_config
from chatpilot.sdk.session_manager import session_manager
from chatpilot.server.webhook import router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle."""

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
        route_config = load_route_config(routes_path)
        app.state.route_config = route_config
        logger.info(
            "Route config loaded: %d platform(s) from %s",
            len(route_config.platforms),
            routes_path,
        )

        # Validate agent names in agentList
        for name in route_config.agent_list:
            if name not in agent_registry:
                raise RouteError(f"unknown agent in agentList: {name}")
    except FileNotFoundError:
        from chatpilot.core.types import RouteConfig

        logger.warning(
            "Routes file not found: %s — starting with empty config", routes_path
        )
        route_config = RouteConfig(agent_list=[], platforms={})
        app.state.route_config = route_config

    # Timeout config
    timeout_s = int(os.environ.get("REPLY_TIMEOUT_MS", "20000")) / 1000.0

    # Create and store the processor (lazy import to avoid circular dependency)
    from chatpilot.processing.processor import MessageProcessor

    processor = MessageProcessor(route_config, routes_path, agent_registry, timeout_s)
    app.state.processor = processor

    # RouteWatcher disabled until Task 7 migrates it to new schema
    logger.info(
        "RouteWatcher disabled (pending migration to RouteConfig schema)"
    )

    logger.info("Server started. Webhook endpoint: POST /webhook/{platform}")

    yield

    # Shutdown
    await session_manager.stop()
    logger.info("[SHUTDOWN] server stopped")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(title="ChatPilot Agent Gateway", lifespan=lifespan)
    app.include_router(router)
    return app


app = create_app()
