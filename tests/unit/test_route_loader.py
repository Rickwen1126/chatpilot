"""Unit tests for route loader — new RouteConfig schema."""

import os
import tempfile

from chatpilot.dispatch.route_loader import load_route_config, save_route_config


def test_load_route_config_valid():
    yaml_content = """
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
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(yaml_content)
        f.flush()
        config = load_route_config(f.name)
    os.unlink(f.name)

    assert config.agent_list == ["general-agent", "warehouse-agent"]
    assert config.platforms["line"].default_agent == "general-agent"
    null_route = config.platforms["line"].conversation_routes["null"]
    assert null_route.agent == "general-agent"
    assert null_route.model == "claude-haiku-4.5"


def test_load_route_config_empty():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write("")
        f.flush()
        config = load_route_config(f.name)
    os.unlink(f.name)

    assert config.agent_list == []
    assert config.platforms == {}


def test_save_and_reload():
    yaml_content = """
agentList:
  - general-agent
platforms:
  mock:
    defaultAgent: general-agent
    conversationRoutes:
      "null":
        agent: general-agent
        model: gpt-4.1
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(yaml_content)
        f.flush()
        path = f.name

    config = load_route_config(path)
    config.platforms["mock"].conversation_routes["null"].model = "claude-haiku-4.5"
    save_route_config(path, config)

    reloaded = load_route_config(path)
    assert reloaded.platforms["mock"].conversation_routes["null"].model == "claude-haiku-4.5"

    os.unlink(path)
