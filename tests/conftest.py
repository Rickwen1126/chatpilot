"""Shared test fixtures for v2."""

import pytest

from chatpilot.core.types import Message, Response


@pytest.fixture
def mock_message():
    return Message(
        text="你好",
        user_id="U123",
        platform="line",
        conversation_id="C456",
        group_id="C456",
        is_mention=True,
        platform_context={"reply_token": "token123", "message_id": "msg789"},
    )


@pytest.fixture
def mock_private_message():
    return Message(
        text="你好",
        user_id="U123",
        platform="line",
        conversation_id="U123",
    )


@pytest.fixture
def mock_response():
    return Response(text="Hello from chatbot!")
