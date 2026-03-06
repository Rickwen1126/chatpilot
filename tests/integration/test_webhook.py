"""Integration tests for webhook endpoint using mock adapter."""

import json

import pytest
from httpx import ASGITransport, AsyncClient

from chatpilot.core.types import (
    ConversationRoute,
    Message,
    PlatformConfig,
    Response,
    RouteConfig,
)


@pytest.fixture
def mock_app():
    from fastapi import FastAPI

    from chatpilot.agents import agent_registry, register_agent
    from chatpilot.channels.adapter import AdapterRegistry
    from chatpilot.channels.mock import mock_adapter
    from chatpilot.processing.processor import MessageProcessor
    from chatpilot.server.webhook import router

    app = FastAPI()
    app.include_router(router)

    adapter_registry: AdapterRegistry = {"mock": mock_adapter}
    app.state.adapter_registry = adapter_registry

    route_config = RouteConfig(
        agent_list=["test-agent"],
        platforms={
            "mock": PlatformConfig(
                default_agent="test-agent",
                conversation_routes={
                    "c1": ConversationRoute(agent="test-agent", model="gpt-4.1"),
                },
            ),
        },
    )

    class TestAgent:
        @property
        def name(self) -> str:
            return "test-agent"

        async def handle(
            self, message: Message, session_id: str,
            model: str | None = None, workdir: str | None = None,
        ) -> Response:
            return Response(text=f"echo: {message.text}")

    agent_registry.clear()
    register_agent(TestAgent())

    processor = MessageProcessor(route_config, "", agent_registry, timeout_s=20.0)
    app.state.processor = processor

    return app


@pytest.mark.asyncio
async def test_webhook_mock_valid(mock_app):
    async with AsyncClient(
        transport=ASGITransport(app=mock_app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/webhook/mock",
            content=json.dumps(
                {"text": "hello", "userId": "u1", "conversationId": "c1"}
            ),
            headers={"content-type": "application/json"},
        )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_webhook_unknown_platform(mock_app):
    async with AsyncClient(
        transport=ASGITransport(app=mock_app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/webhook/unknown",
            content=b"{}",
        )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_webhook_command_handled(mock_app):
    """Slash command should be handled without reaching the agent."""
    async with AsyncClient(
        transport=ASGITransport(app=mock_app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/webhook/mock",
            content=json.dumps(
                {"text": "/agent", "userId": "u1", "conversationId": "c1"}
            ),
            headers={"content-type": "application/json"},
        )
    assert resp.status_code == 200
