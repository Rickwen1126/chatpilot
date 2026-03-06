"""Shared test fixtures."""

import pytest

from chatpilot.core.types import (
    ConversationRoute,
    LinePlatformContext,
    Message,
    PlatformConfig,
    Response,
    RouteConfig,
)


@pytest.fixture
def mock_message():
    return Message(
        text="你好",
        user_id="U123",
        platform="line",
        conversation_id="C456",
        platform_context=LinePlatformContext(
            reply_token="token123",
            message_id="msg789",
            timestamp=1700000000000,
        ),
    )


@pytest.fixture
def mock_private_message():
    return Message(
        text="你好",
        user_id="U123",
        platform="line",
        conversation_id=None,
    )


@pytest.fixture
def mock_response():
    return Response(text="Hello from agent!")


@pytest.fixture
def mock_route_config():
    return RouteConfig(
        agent_list=["general-agent", "warehouse-agent"],
        platforms={
            "line": PlatformConfig(
                default_agent="general-agent",
                conversation_routes={
                    "null": ConversationRoute(
                        agent="general-agent",
                        model="claude-haiku-4.5",
                    ),
                    "C456": ConversationRoute(
                        agent="general-agent",
                        model="claude-haiku-4.5",
                    ),
                },
            ),
        },
    )


@pytest.fixture
def mock_agent_registry():
    class StubAgent:
        def __init__(self, name: str):
            self._name = name

        @property
        def name(self) -> str:
            return self._name

        async def handle(
            self, message, session_id: str,
            model: str | None = None, workdir: str | None = None,
        ):
            return Response(text=f"[{self._name}] reply")

    return {
        "general-agent": StubAgent("general-agent"),
        "warehouse-agent": StubAgent("warehouse-agent"),
    }
