"""Mention filter — determines if a message is directed at the bot."""

from __future__ import annotations

import re

from chatpilot.core.types import Message

# Module-level keyword patterns, set by configure()
_keyword_patterns: list[re.Pattern] = []

# Per-chatbot auto-trigger patterns: chatbot_name → [compiled regex]
_auto_trigger_map: dict[str, list[re.Pattern]] = {}


def configure(keywords: list[str]) -> None:
    """Set global trigger keywords from config. Called once at startup."""
    global _keyword_patterns
    _keyword_patterns = [
        re.compile(rf"^{re.escape(kw)}\s", re.IGNORECASE)
        for kw in keywords
        if kw.strip()
    ]


def configure_auto_triggers(
    chatbot_keywords: dict[str, list[str]],
) -> None:
    """Set per-chatbot auto-trigger keywords. Called once at startup.

    chatbot_keywords: {chatbot_name: [keyword1, keyword2, ...]}
    """
    global _auto_trigger_map
    _auto_trigger_map = {}
    for name, keywords in chatbot_keywords.items():
        patterns = [
            re.compile(re.escape(kw), re.IGNORECASE)
            for kw in keywords
            if kw.strip()
        ]
        if patterns:
            _auto_trigger_map[name] = patterns


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


def match_auto_trigger(
    message: Message, bound_chatbot: str | None
) -> bool:
    """Check if message matches auto-trigger keywords for the bound chatbot.

    Only checks keywords of the chatbot bound to this conversation.
    Returns True if any keyword found anywhere in message text.
    """
    if message.group_id is None:
        return False  # Private chat already handled by is_mention
    if not bound_chatbot:
        return False
    patterns = _auto_trigger_map.get(bound_chatbot, [])
    for pattern in patterns:
        if pattern.search(message.text):
            return True
    return False
