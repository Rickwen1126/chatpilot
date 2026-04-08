"""Tests for tool factory."""

import pytest

from chatpilot.core.types import AccessLevel, ToolDefinition
from chatpilot.tools.factory import ToolFactory


def _tool(name: str, access: AccessLevel = AccessLevel.GLOBAL):
    return ToolDefinition(
        name=name,
        description=f"Test tool {name}",
        parameters={"type": "object", "properties": {}},
        handler=lambda: None,
        access_level=access,
    )


def test_register_and_list():
    f = ToolFactory()
    f.register(_tool("a"))
    f.register(_tool("b"))
    assert len(f.list_tools()) == 2


def test_register_duplicate_raises():
    f = ToolFactory()
    f.register(_tool("a"))
    with pytest.raises(ValueError):
        f.register(_tool("a"))


def test_get_tools_for_chatbot():
    f = ToolFactory()
    f.register(_tool("global_t", AccessLevel.GLOBAL))
    f.register(_tool("chat_t", AccessLevel.CHATBOT_ONLY))
    f.register(_tool("agent_t", AccessLevel.AGENT_TEAM_ONLY))
    result = f.get_tools_for_chatbot(["global_t", "chat_t", "agent_t"])
    names = {t.name for t in result}
    assert names == {"global_t", "chat_t"}


def test_get_tools_for_pipeline():
    f = ToolFactory()
    f.register(_tool("global_t", AccessLevel.GLOBAL))
    f.register(_tool("agent_t", AccessLevel.AGENT_TEAM_ONLY))
    f.register(_tool("chat_t", AccessLevel.CHATBOT_ONLY))
    result = f.get_tools_for_pipeline(["global_t", "agent_t"])
    names = {t.name for t in result}
    assert names == {"global_t", "agent_t"}


def test_pipeline_rejects_agent_team_trigger():
    f = ToolFactory()
    f.register(_tool("submit", AccessLevel.AGENT_TEAM_TRIGGER))
    with pytest.raises(ValueError):
        f.get_tools_for_pipeline(["submit"])


def test_chatbot_allows_agent_team_trigger():
    f = ToolFactory()
    f.register(_tool("submit", AccessLevel.AGENT_TEAM_TRIGGER))
    result = f.get_tools_for_chatbot(["submit"])
    assert len(result) == 1
    assert result[0].name == "submit"


def test_get_tools_for_observer():
    f = ToolFactory()
    f.register(_tool("global_t", AccessLevel.GLOBAL))
    f.register(_tool("observer_t", AccessLevel.OBSERVER_ONLY))
    f.register(_tool("chat_t", AccessLevel.CHATBOT_ONLY))
    f.register(_tool("agent_t", AccessLevel.AGENT_TEAM_ONLY))
    result = f.get_tools_for_observer(
        ["global_t", "observer_t", "chat_t", "agent_t"]
    )
    names = {t.name for t in result}
    assert names == {"global_t", "observer_t"}
