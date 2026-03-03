"""Unit tests for the dispatcher — 3-phase lookup."""

from chatpilot.core.types import (
    FallbackMatch,
    Ignored,
    KeywordMatch,
    Message,
    RouteMap,
)
from chatpilot.dispatch.dispatcher import dispatch


def test_keyword_match(mock_message, mock_route_map, mock_agent_registry):
    """Keyword "庫存" should route to warehouse-agent."""
    msg = mock_message.model_copy(update={"text": "請查庫存"})
    result, agent = dispatch(msg, mock_route_map, mock_agent_registry)
    assert isinstance(result, KeywordMatch)
    assert result.agent_name == "warehouse-agent"
    assert result.keyword == "庫存"
    assert agent is not None
    assert agent.name == "warehouse-agent"


def test_fallback_match(mock_message, mock_route_map, mock_agent_registry):
    """No keyword match should use fallback agent."""
    msg = mock_message.model_copy(update={"text": "今天天氣好"})
    result, agent = dispatch(msg, mock_route_map, mock_agent_registry)
    assert isinstance(result, FallbackMatch)
    assert result.agent_name == "general-agent"
    assert agent is not None


def test_ignored_no_route(mock_route_map, mock_agent_registry):
    """Message from unregistered group should be ignored."""
    msg = Message(text="hello", user_id="U1", platform="line", conversation_id="CUNKNOWN")
    result, agent = dispatch(msg, mock_route_map, mock_agent_registry)
    assert isinstance(result, Ignored)
    assert result.reason == "no_route"
    assert agent is None


def test_ignored_no_fallback(mock_route_map, mock_agent_registry):
    """Group C789 has no fallback — should ignore."""
    msg = Message(text="hello", user_id="U1", platform="line", conversation_id="C789")
    result, agent = dispatch(msg, mock_route_map, mock_agent_registry)
    assert isinstance(result, Ignored)
    assert result.reason == "no_fallback"
    assert agent is None


def test_private_chat_fallback(mock_private_message, mock_route_map, mock_agent_registry):
    """Private chat (conversation_id=None) should use (platform, None) rule."""
    result, agent = dispatch(mock_private_message, mock_route_map, mock_agent_registry)
    assert isinstance(result, FallbackMatch)
    assert result.agent_name == "general-agent"
    assert agent is not None


def test_empty_routes(mock_message, mock_agent_registry):
    """Empty route map should ignore all messages."""
    empty_map = RouteMap(routes=[])
    result, agent = dispatch(mock_message, empty_map, mock_agent_registry)
    assert isinstance(result, Ignored)
    assert agent is None
