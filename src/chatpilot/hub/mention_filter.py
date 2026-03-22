"""Mention filter — determines if a message is directed at the bot."""

from __future__ import annotations

from chatpilot.core.types import Message


def is_mention(message: Message) -> bool:
    """Check if a message is directed at the bot.

    - Private chat (no group_id): always True
    - Group chat: check is_mention flag
    """
    if message.group_id is None:
        return True
    return message.is_mention
