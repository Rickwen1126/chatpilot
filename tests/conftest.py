"""Shared test fixtures."""

import pytest

from chatpilot.core.types import (
    FallbackMatch,
    Ignored,
    KeywordMapping,
    KeywordMatch,
    LinePlatformContext,
    Message,
    Response,
    RouteMap,
    RouteRule,
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
def mock_route_map():
    return RouteMap(
        routes=[
            RouteRule(
                platform="line",
                conversation_id="C456",
                keywords=[
                    KeywordMapping(keyword="庫存", agent_name="warehouse-agent"),
                    KeywordMapping(keyword="報表", agent_name="report-agent"),
                ],
                fallback_agent="general-agent",
            ),
            RouteRule(
                platform="line",
                conversation_id="C789",
                keywords=[],
                fallback_agent=None,
            ),
            RouteRule(
                platform="line",
                conversation_id=None,
                keywords=[],
                fallback_agent="general-agent",
            ),
        ]
    )


@pytest.fixture
def mock_agent_registry():
    """Minimal agent registry for testing dispatch logic."""

    class StubAgent:
        def __init__(self, name: str):
            self._name = name

        @property
        def name(self) -> str:
            return self._name

        async def handle(self, message, session_id: str, model: str | None = None, workdir: str | None = None):
            return Response(text=f"[{self._name}] reply")

    return {
        "general-agent": StubAgent("general-agent"),
        "warehouse-agent": StubAgent("warehouse-agent"),
        "report-agent": StubAgent("report-agent"),
    }
