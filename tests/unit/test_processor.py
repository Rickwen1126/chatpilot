"""Unit tests for MessageProcessor."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from chatpilot.core.types import (
    ConversationRoute,
    Message,
    PlatformConfig,
    Response,
    RouteConfig,
)
from chatpilot.processing.processor import MessageProcessor


def _make_config() -> RouteConfig:
    return RouteConfig(
        agent_list=["general-agent", "warehouse-agent"],
        platforms={
            "mock": PlatformConfig(
                default_agent="general-agent",
                conversation_routes={
                    "null": ConversationRoute(
                        agent="general-agent",
                        model="gpt-4.1",
                        workdir="~/code",
                    ),
                    "c1": ConversationRoute(
                        agent="warehouse-agent",
                        model="claude-haiku-4.5",
                    ),
                },
            ),
        },
    )


def _make_msg(text: str = "hello", conversation_id: str | None = None) -> Message:
    return Message(
        text=text,
        user_id="U1",
        platform="mock",
        conversation_id=conversation_id,
    )


def _make_agent(name: str = "general-agent", response_text: str = "ok") -> MagicMock:
    agent = MagicMock()
    agent.name = name
    agent.handle = AsyncMock(return_value=Response(text=response_text))
    return agent


def _make_adapter() -> MagicMock:
    adapter = MagicMock()
    adapter.send_response = AsyncMock()
    adapter.send_processing_ack = AsyncMock()
    return adapter


@pytest.mark.asyncio
async def test_command_handled():
    """Slash commands should be handled by CommandHandler, not reach the agent."""
    config = _make_config()
    agent = _make_agent()
    agents = {"general-agent": agent}
    processor = MessageProcessor(config, "", agents, timeout_s=20.0)

    adapter = _make_adapter()
    msg = _make_msg("/agent")

    await processor.process(msg, adapter)

    adapter.send_response.assert_called_once()
    reply = adapter.send_response.call_args[0][1].text
    assert "general-agent" in reply
    agent.handle.assert_not_called()


@pytest.mark.asyncio
async def test_route_to_default_agent():
    """Private chat with null route should go to general-agent."""
    config = _make_config()
    agent = _make_agent("general-agent", "hi there")
    agents = {"general-agent": agent}
    processor = MessageProcessor(config, "", agents, timeout_s=20.0)

    adapter = _make_adapter()
    msg = _make_msg("hello")  # conversation_id=None → key="null"

    await processor.process(msg, adapter)

    agent.handle.assert_called_once()
    adapter.send_response.assert_called_once()


@pytest.mark.asyncio
async def test_route_to_conversation_agent():
    """Message to conversation c1 should go to warehouse-agent."""
    config = _make_config()
    wh_agent = _make_agent("warehouse-agent", "inventory data")
    agents = {"warehouse-agent": wh_agent, "general-agent": _make_agent()}
    processor = MessageProcessor(config, "", agents, timeout_s=20.0)

    adapter = _make_adapter()
    msg = _make_msg("查庫存", conversation_id="c1")

    await processor.process(msg, adapter)

    wh_agent.handle.assert_called_once()


@pytest.mark.asyncio
async def test_unknown_platform_ignored():
    """Message from unregistered platform should be silently ignored."""
    config = _make_config()
    processor = MessageProcessor(config, "", {}, timeout_s=20.0)

    adapter = _make_adapter()
    msg = Message(text="hello", user_id="U1", platform="telegram", conversation_id=None)

    await processor.process(msg, adapter)

    adapter.send_response.assert_not_called()


@pytest.mark.asyncio
async def test_gate_blocks_concurrent():
    """Second message while first is processing should be blocked by gate."""
    config = _make_config()

    slow_agent = MagicMock()
    slow_agent.name = "general-agent"

    async def slow_handle(*args, **kwargs):
        await asyncio.sleep(0.5)
        return Response(text="done")

    slow_agent.handle = slow_handle
    agents = {"general-agent": slow_agent}
    processor = MessageProcessor(config, "", agents, timeout_s=5.0)

    adapter = _make_adapter()
    msg1 = _make_msg("first")
    msg2 = _make_msg("second")

    # Start first message processing (don't await)
    task = asyncio.create_task(processor.process(msg1, adapter))
    await asyncio.sleep(0.05)  # Let it acquire the gate

    # Second message should be gated
    await processor.process(msg2, adapter)

    # Second call should get "處理中" response
    calls = adapter.send_response.call_args_list
    assert any("處理中" in str(call) for call in calls)

    await task
