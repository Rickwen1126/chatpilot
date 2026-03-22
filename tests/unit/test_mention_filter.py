"""Tests for mention filter."""

from chatpilot.core.types import Message
from chatpilot.hub.mention_filter import is_mention


def _msg(group_id=None, mention=False):
    return Message(
        text="test",
        user_id="u1",
        platform="line",
        conversation_id=group_id or "u1",
        group_id=group_id,
        is_mention=mention,
    )


def test_private_chat_always_mention():
    assert is_mention(_msg()) is True


def test_group_not_mentioned():
    assert is_mention(_msg(group_id="g1", mention=False)) is False


def test_group_mentioned():
    assert is_mention(_msg(group_id="g1", mention=True)) is True
