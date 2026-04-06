"""Unit tests for ChatbotSession runtime model reporting."""

from __future__ import annotations

from chatpilot.chatbot.session import ChatbotSession
from chatpilot.core.types import ChatbotConfig


class _StubSdkSession:
    def __init__(self) -> None:
        self.session_id = "sid-1"

    async def send_and_wait(self, message: str, timeout: float = 60.0) -> str:
        return "ok"

    async def destroy(self) -> None:
        return None

    async def get_current_model(self) -> str | None:
        return "gpt-5.4"


def _config() -> ChatbotConfig:
    return ChatbotConfig(
        name="buddy",
        model="gpt-4.1",
        system_message="hi",
        tools=[],
    )


def test_chatbot_session_reports_effective_and_configured_models():
    session = ChatbotSession(
        _StubSdkSession(),
        _config(),
        effective_model="gpt-5.4",
    )

    assert session.model == "gpt-5.4"
    assert session.configured_model == "gpt-4.1"
