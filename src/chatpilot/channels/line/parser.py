"""LINE webhook event parser."""

from __future__ import annotations

import logging

from linebot.v3.webhooks import MessageEvent, TextMessageContent

from chatpilot.core.types import LinePlatformContext, Message

logger = logging.getLogger(__name__)


def parse_line_events(raw_body: bytes, events: list) -> list[Message]:
    """Parse LINE webhook events into Message list.

    Args:
        raw_body: Raw HTTP body (unused, kept for interface consistency)
        events: Parsed LINE webhook events from WebhookParser

    Returns:
        List of Message objects (only text messages; non-text filtered out)
    """
    messages: list[Message] = []
    for event in events:
        if not isinstance(event, MessageEvent):
            continue
        if not isinstance(event.message, TextMessageContent):
            continue

        # Extract conversation_id: groupId > roomId > None (private chat)
        source = event.source
        conversation_id = None
        if hasattr(source, "group_id") and source.group_id:
            conversation_id = source.group_id
        elif hasattr(source, "room_id") and source.room_id:
            conversation_id = source.room_id

        user_id = source.user_id if hasattr(source, "user_id") else ""

        msg = Message(
            text=event.message.text,
            user_id=user_id,
            platform="line",
            conversation_id=conversation_id,
            platform_context=LinePlatformContext(
                reply_token=event.reply_token,
                message_id=event.message.id,
                timestamp=int(event.timestamp) if event.timestamp else 0,
            ),
        )
        messages.append(msg)
    return messages
