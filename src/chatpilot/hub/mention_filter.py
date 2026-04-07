"""Mention filter — determines if a message is directed at the bot.

Two-layer keyword system:
- Layer 1 (_chatbot_keywords): per-bot config seed, loaded from route settings
- Layer 2 (_route_keywords): per-channel DB additions, write-through cache
"""

from __future__ import annotations

import logging
import re

from chatpilot.core.types import Message

logger = logging.getLogger(__name__)

# Module-level keyword patterns, set by configure()
_keyword_patterns: list[re.Pattern] = []

# Layer 1: per-chatbot auto-trigger patterns from config
_chatbot_keywords: dict[str, list[re.Pattern]] = {}

# Layer 2: per-route trigger keywords from DB (write-through cache)
_route_keywords: dict[str, list[re.Pattern]] = {}

# Raw keyword strings for DB layer (for listing/validation)
_route_keywords_raw: dict[str, list[str]] = {}

MAX_ROUTE_KEYWORDS = 20
MIN_KEYWORD_LENGTH = 2


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
    """Set per-chatbot auto-trigger keywords from config.

    chatbot_keywords: {chatbot_name: [keyword1, keyword2, ...]}
    """
    global _chatbot_keywords
    _chatbot_keywords = {}
    for name, keywords in chatbot_keywords.items():
        patterns = [
            re.compile(re.escape(kw), re.IGNORECASE)
            for kw in keywords
            if kw.strip()
        ]
        if patterns:
            _chatbot_keywords[name] = patterns


def load_route_keywords(all_keywords: dict[str, list[str]]) -> None:
    """Load all per-route keywords from DB into cache.

    Called once at startup. all_keywords: {route_id: [keyword, ...]}
    """
    global _route_keywords, _route_keywords_raw
    _route_keywords = {}
    _route_keywords_raw = {}
    for route_id, keywords in all_keywords.items():
        _route_keywords_raw[route_id] = list(keywords)
        _route_keywords[route_id] = [
            re.compile(re.escape(kw), re.IGNORECASE)
            for kw in keywords
            if kw.strip()
        ]
    if all_keywords:
        total = sum(len(v) for v in all_keywords.values())
        logger.info(
            "Loaded %d route keywords across %d routes",
            total, len(all_keywords),
        )


def add_route_keyword(route_id: str, keyword: str) -> None:
    """Add a keyword to the in-memory cache (after DB write succeeded)."""
    raw = _route_keywords_raw.setdefault(route_id, [])
    if keyword not in raw:
        raw.append(keyword)
    patterns = _route_keywords.setdefault(route_id, [])
    patterns.append(re.compile(re.escape(keyword), re.IGNORECASE))
    logger.info("Route keyword added: %s → '%s'", route_id[:16], keyword)


def remove_route_keyword(route_id: str, keyword: str) -> None:
    """Remove a keyword from the in-memory cache (after DB delete succeeded)."""
    raw = _route_keywords_raw.get(route_id, [])
    if keyword in raw:
        raw.remove(keyword)
    # Rebuild patterns for this route (simpler than finding the exact pattern)
    _route_keywords[route_id] = [
        re.compile(re.escape(kw), re.IGNORECASE)
        for kw in raw
    ]
    logger.info("Route keyword removed: %s → '%s'", route_id[:16], keyword)


def get_route_keywords(route_id: str) -> list[str]:
    """Get raw keyword strings for a route (for listing/validation)."""
    return list(_route_keywords_raw.get(route_id, []))


def get_config_keywords(chatbot_name: str) -> list[str]:
    """Get config keyword strings for a chatbot (for display only)."""
    patterns = _chatbot_keywords.get(chatbot_name, [])
    return [p.pattern.replace("\\", "") for p in patterns]


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
    """Check if message matches auto-trigger keywords.

    Checks two layers:
    1. Config keywords (per-chatbot) — shared across all routes of this bot
    2. DB keywords (per-route) — specific to this channel

    Returns True if any keyword found anywhere in message text.
    """
    if message.group_id is None:
        return False  # Private chat already handled by is_mention
    if not bound_chatbot:
        return False

    # Layer 1: config keywords (per-chatbot)
    for pattern in _chatbot_keywords.get(bound_chatbot, []):
        if pattern.search(message.text):
            logger.info(
                "[mention] auto-trigger HIT config keyword='%s' bot=%s",
                pattern.pattern, bound_chatbot,
            )
            return True

    # Layer 2: DB keywords (per-route)
    route_id = f"{message.platform}:{message.conversation_id}"
    for pattern in _route_keywords.get(route_id, []):
        if pattern.search(message.text):
            logger.info(
                "[mention] auto-trigger HIT route keyword='%s' route=%s",
                pattern.pattern, route_id,
            )
            return True

    logger.debug(
        "[mention] auto-trigger MISS bot=%s route=%s text=%s",
        bound_chatbot, route_id, message.text[:50],
    )
    return False
