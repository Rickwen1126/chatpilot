"""Unit tests for CommandHandler — /agent and /model commands."""

import os
import tempfile

import yaml

from chatpilot.core.types import (
    ConversationRoute,
    Message,
    PlatformConfig,
    RouteConfig,
)
from chatpilot.processing.command_handler import CommandHandler


def _make_config() -> RouteConfig:
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
                },
            ),
        },
    )


def _make_msg(text: str, conversation_id: str | None = None) -> Message:
    return Message(
        text=text,
        user_id="U123",
        platform="line",
        conversation_id=conversation_id,
    )


def test_not_a_command():
    handler = CommandHandler()
    config = _make_config()
    result = handler.try_handle(_make_msg("hello"), config, "")
    assert result is None


def test_agent_list():
    handler = CommandHandler()
    config = _make_config()
    result = handler.try_handle(_make_msg("/agent"), config, "")
    assert result is not None
    assert "general-agent" in result
    assert "warehouse-agent" in result


def test_agent_switch():
    handler = CommandHandler()
    config = _make_config()
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(config.model_dump(by_alias=True), f)
        path = f.name

    result = handler.try_handle(_make_msg("/agent warehouse"), config, path)
    assert result is not None
    assert "warehouse" in result.lower()
    # Verify config updated in-memory
    route = config.platforms["line"].conversation_routes["null"]
    assert route.agent == "warehouse-agent"

    os.unlink(path)


def test_agent_switch_unknown():
    handler = CommandHandler()
    config = _make_config()
    result = handler.try_handle(_make_msg("/agent unknown-agent"), config, "")
    assert result is not None
    assert "找不到" in result


def test_model_show_current():
    handler = CommandHandler()
    config = _make_config()
    result = handler.try_handle(_make_msg("/model"), config, "")
    assert result is not None
    assert "claude-haiku-4.5" in result


def test_model_switch():
    handler = CommandHandler()
    config = _make_config()
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(config.model_dump(by_alias=True), f)
        path = f.name

    result = handler.try_handle(_make_msg("/model sonnet"), config, path)
    assert result is not None
    assert "claude-sonnet-4.6" in result
    route = config.platforms["line"].conversation_routes["null"]
    assert route.model == "claude-sonnet-4.6"

    os.unlink(path)
