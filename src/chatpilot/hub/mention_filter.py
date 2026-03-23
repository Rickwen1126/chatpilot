"""Mention filter — determines if a message is directed at the bot."""

from __future__ import annotations

import re

from chatpilot.core.types import Message

# Module-level keyword patterns, set by configure()
_keyword_patterns: list[re.Pattern] = []


def configure(keywords: list[str]) -> None:
    """Set trigger keywords from config. Called once at startup."""
    global _keyword_patterns
    _keyword_patterns = [
        re.compile(rf"^{re.escape(kw)}\s", re.IGNORECASE)
        for kw in keywords
        if kw.strip()
    ]


def is_mention(message: Message) -> bool:
    """Check if a message is directed at the bot.

    - Private chat (no group_id): always True
    - Group chat: check @bot mention flag OR keyword trigger
    """
    if message.group_id is None:
        return True
    if message.is_mention:
        return True
    # Check keyword triggers (e.g. "bot 你好" → True)
    for pattern in _keyword_patterns:
        if pattern.search(message.text):
            return True
    return False
