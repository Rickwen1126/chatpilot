"""LINE webhook event parser."""

from __future__ import annotations

import logging

from linebot.v3.webhooks import MentionTarget, MessageEvent, TextMessageContent

from chatpilot.core.types import Message

logger = logging.getLogger(__name__)


def parse_line_events(events: list) -> list[Message]:
    """Parse LINE webhook events into unified Message list.

    Extracts is_mention and user_name from LINE-specific fields.
    """
    messages: list[Message] = []
    for event in events:
        if not isinstance(event, MessageEvent):
            continue
        if not isinstance(event.message, TextMessageContent):
            continue

        source = event.source
        group_id: str | None = None
        if hasattr(source, "group_id") and source.group_id:
            group_id = source.group_id
        elif hasattr(source, "room_id") and source.room_id:
            group_id = source.room_id

        user_id = source.user_id if hasattr(source, "user_id") else ""
        conversation_id = group_id or user_id

        # Detect @bot mention
        is_mention = False
        mention = getattr(event.message, "mention", None)
        if mention and hasattr(mention, "mentionees"):
            for m in mention.mentionees:
                if isinstance(m, MentionTarget) and getattr(m, "is_self", False):
                    is_mention = True
                    break

        msg = Message(
            text=event.message.text,
            user_id=user_id,
            user_name="",  # LINE needs profile API for name; leave empty for MVP
            platform="line",
            group_id=group_id,
            conversation_id=conversation_id,
            is_mention=is_mention,
            platform_context={
                "reply_token": event.reply_token,
                "message_id": event.message.id,
            },
        )
        messages.append(msg)
    return messages
