"""Tests for context buffer."""

from datetime import datetime, timezone

from chatpilot.core.types import ContextMessage, ContextMessageType
from chatpilot.hub.context_buffer import ContextBuffer


def _ctx_msg(text="hello", msg_type=ContextMessageType.background):
    return ContextMessage(
        user_id="u1",
        user_name="User1",
        text=text,
        timestamp=datetime(2026, 1, 1, 14, 30, tzinfo=timezone.utc),
        message_type=msg_type,
    )


def test_append_and_drain():
    buf = ContextBuffer(default_window=10)
    buf.append("r1", _ctx_msg("a"))
    buf.append("r1", _ctx_msg("b"))
    messages = buf.drain("r1")
    assert len(messages) == 2
    assert messages[0].text == "a"
    # Drain empties the buffer
    assert buf.drain("r1") == []


def test_sliding_window():
    buf = ContextBuffer(default_window=2)
    buf.append("r1", _ctx_msg("a"))
    buf.append("r1", _ctx_msg("b"))
    buf.append("r1", _ctx_msg("c"))
    messages = buf.drain("r1")
    assert len(messages) == 2
    assert messages[0].text == "b"
    assert messages[1].text == "c"


def test_format_context():
    buf = ContextBuffer()
    messages = [
        _ctx_msg("聊天", ContextMessageType.background),
        _ctx_msg("@bot 幫忙", ContextMessageType.background),
    ]
    result = buf.format_context(messages)
    assert "[背景]" in result
    assert "[背景]" in result
    assert "---" in result


def test_format_context_empty():
    buf = ContextBuffer()
    assert buf.format_context([]) == ""
