"""Unit tests for route loader — YAML parse and hot-reload."""

import os
import tempfile

from chatpilot.dispatch.route_loader import load_routes


def test_load_routes_valid_yaml():
    """Valid YAML should parse into RouteMap."""
    yaml_content = """
routes:
  - platform: line
    conversationId: "C123"
    keywords:
      - keyword: "test"
        agentName: general-agent
    fallbackAgent: general-agent
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(yaml_content)
        f.flush()
        route_map = load_routes(f.name)
    os.unlink(f.name)

    assert len(route_map.routes) == 1
    assert route_map.routes[0].platform == "line"
    assert route_map.routes[0].conversation_id == "C123"
    assert route_map.routes[0].fallback_agent == "general-agent"
    assert len(route_map.routes[0].keywords) == 1
    assert route_map.routes[0].keywords[0].keyword == "test"
    assert route_map.routes[0].keywords[0].agent_name == "general-agent"


def test_load_routes_empty_yaml():
    """Empty YAML should return empty RouteMap."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write("")
        f.flush()
        route_map = load_routes(f.name)
    os.unlink(f.name)

    assert len(route_map.routes) == 0


def test_load_routes_null_conversation_id():
    """Null conversationId should parse as None (private chat rule)."""
    yaml_content = """
routes:
  - platform: line
    conversationId: null
    keywords: []
    fallbackAgent: general-agent
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(yaml_content)
        f.flush()
        route_map = load_routes(f.name)
    os.unlink(f.name)

    assert route_map.routes[0].conversation_id is None
    assert route_map.routes[0].fallback_agent == "general-agent"
