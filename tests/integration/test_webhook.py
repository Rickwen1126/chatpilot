"""Integration tests for webhook endpoint using mock adapter."""

import json
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from chatpilot.channels.mock import MockAdapter
from chatpilot.core.types import Message, Response, RouteMap, RouteRule


@pytest.fixture
def mock_app():
    """Create a minimal FastAPI app for testing without Copilot SDK."""
    from fastapi import FastAPI

    from chatpilot.agents import agent_registry, register_agent
    from chatpilot.channels.adapter import AdapterRegistry
    from chatpilot.channels.mock import mock_adapter
    from chatpilot.server.webhook import router

    app = FastAPI()
    app.include_router(router)

    # Set up state
    adapter_registry: AdapterRegistry = {"mock": mock_adapter}
    app.state.adapter_registry = adapter_registry
    app.state.reply_timeout_ms = 20000

    # Minimal route map for mock platform
    app.state.route_map = RouteMap(
        routes=[
            RouteRule(
                platform="mock",
                conversation_id="c1",
                keywords=[],
                fallback_agent="test-agent",
            )
        ]
    )

    # Register a test agent
    class TestAgent:
        @property
        def name(self) -> str:
            return "test-agent"

        async def handle(self, message: Message, session_id: str) -> Response:
            return Response(text=f"echo: {message.text}")

    # Clear and register
    agent_registry.clear()
    register_agent(TestAgent())

    return app


@pytest.mark.asyncio
async def test_webhook_mock_valid(mock_app):
    """POST /webhook/mock with valid body should return 200."""
    async with AsyncClient(
        transport=ASGITransport(app=mock_app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/webhook/mock",
            content=json.dumps({"text": "hello", "userId": "u1", "conversationId": "c1"}),
            headers={"content-type": "application/json"},
        )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_webhook_unknown_platform(mock_app):
    """POST /webhook/unknown should return 400."""
    async with AsyncClient(
        transport=ASGITransport(app=mock_app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/webhook/unknown",
            content=b"{}",
        )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_webhook_mock_ignored_route(mock_app):
    """Message from unrouted conversation should be silently ignored."""
    async with AsyncClient(
        transport=ASGITransport(app=mock_app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/webhook/mock",
            content=json.dumps({"text": "hello", "userId": "u1", "conversationId": "unknown-group"}),
            headers={"content-type": "application/json"},
        )
    assert resp.status_code == 200
