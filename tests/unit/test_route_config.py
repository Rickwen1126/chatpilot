"""Unit tests for RouteConfig schema."""

import yaml

from chatpilot.core.types import ConversationRoute, PlatformConfig, RouteConfig


def test_conversation_route_basic():
    route = ConversationRoute(agent="general-agent", model="gpt-4.1", workdir="~/code")
    assert route.agent == "general-agent"
    assert route.model == "gpt-4.1"
    assert route.workdir == "~/code"


def test_conversation_route_defaults():
    route = ConversationRoute(agent="general-agent")
    assert route.model is None
    assert route.workdir is None


def test_platform_config_from_dict():
    data = {
        "defaultAgent": "general-agent",
        "conversationRoutes": {
            "null": {"agent": "general-agent", "model": "claude-haiku-4.5"},
        },
    }
    config = PlatformConfig.model_validate(data)
    assert config.default_agent == "general-agent"
    assert "null" in config.conversation_routes
    assert config.conversation_routes["null"].agent == "general-agent"


def test_route_config_from_yaml():
    yaml_str = """
agentList:
  - general-agent
  - warehouse-agent
platforms:
  line:
    defaultAgent: general-agent
    conversationRoutes:
      "null":
        agent: general-agent
        model: claude-haiku-4.5
        workdir: ~/code/chatpilot/
  mock:
    defaultAgent: general-agent
    conversationRoutes:
      "null":
        agent: general-agent
        model: gpt-4.1
"""
    data = yaml.safe_load(yaml_str)
    config = RouteConfig.model_validate(data)
    assert config.agent_list == ["general-agent", "warehouse-agent"]
    assert "line" in config.platforms
    assert config.platforms["line"].default_agent == "general-agent"
    null_route = config.platforms["line"].conversation_routes["null"]
    assert null_route.agent == "general-agent"
    assert null_route.model == "claude-haiku-4.5"
    assert null_route.workdir == "~/code/chatpilot/"


def test_route_config_empty_conversation_routes():
    data = {
        "agentList": ["general-agent"],
        "platforms": {
            "line": {"defaultAgent": "general-agent"},
        },
    }
    config = RouteConfig.model_validate(data)
    assert config.platforms["line"].conversation_routes == {}
