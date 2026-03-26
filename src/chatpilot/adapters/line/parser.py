"""LINE webhook event parser."""

from __future__ import annotations

import logging

from linebot.v3.webhooks import (
    FileMessageContent,
    ImageMessageContent,
    MessageEvent,
    TextMessageContent,
    UserMentionee,
)

from chatpilot.core.time_service import TimeService
from chatpilot.core.types import Message

logger = logging.getLogger(__name__)


def parse_line_events(events: list) -> list[Message]:
    """Parse LINE webhook events into unified Message list.

    Handles text messages and image messages.
    Images are represented as text with ref: [圖片 ref:line:{message_id}]
    """
    messages: list[Message] = []
    ts = TimeService.get()
    received_at = ts.utc_now()

    for event in events:
        if not isinstance(event, MessageEvent):
            continue

        source = event.source
        group_id: str | None = None
        if hasattr(source, "group_id") and source.group_id:
            group_id = source.group_id
        elif hasattr(source, "room_id") and source.room_id:
            group_id = source.room_id

        user_id = source.user_id if hasattr(source, "user_id") else ""
        conversation_id = group_id or user_id

        # LINE event.timestamp = epoch ms (UTC) — 訊息真實時間
        event_ts = ts.from_epoch_ms(event.timestamp) if event.timestamp else received_at

        # Detect @bot mention (only on text messages)
        is_mention = False
        if isinstance(event.message, TextMessageContent):
            mention = getattr(event.message, "mention", None)
            logger.info(
                "LINE msg from %s group=%s mention=%s text=%r",
                user_id[:8], group_id, mention, event.message.text[:50],
            )
            if mention and hasattr(mention, "mentionees"):
                for m in mention.mentionees:
                    is_self = getattr(m, "is_self", False) or getattr(m, "isSelf", False)
                    logger.info("  mentionee: type=%s is_self=%s", type(m).__name__, is_self)
                    if isinstance(m, UserMentionee) and is_self:
                        is_mention = True
                        break

            msg = Message(
                text=event.message.text,
                user_id=user_id,
                user_name="",
                platform="line",
                group_id=group_id,
                conversation_id=conversation_id,
                is_mention=is_mention,
                timestamp=event_ts,
                platform_context={
                    "reply_token": event.reply_token,
                    "message_id": event.message.id,
                    "received_at": received_at.isoformat(),
                },
            )
            messages.append(msg)

        elif isinstance(event.message, ImageMessageContent):
            msg = Message(
                text=f"[圖片 ref:line:{event.message.id}]",
                user_id=user_id,
                user_name="",
                platform="line",
                group_id=group_id,
                conversation_id=conversation_id,
                is_mention=False,
                timestamp=event_ts,
                platform_context={
                    "reply_token": event.reply_token,
                    "message_id": event.message.id,
                    "received_at": received_at.isoformat(),
                },
            )
            messages.append(msg)

        elif isinstance(event.message, FileMessageContent):
            fname = event.message.file_name or "file"
            logger.info(
                "LINE file from %s: %s (%d bytes)",
                user_id[:8], fname, event.message.file_size or 0,
            )
            msg = Message(
                text=f"[檔案 ref:line:{event.message.id}:{fname}]",
                user_id=user_id,
                user_name="",
                platform="line",
                group_id=group_id,
                conversation_id=conversation_id,
                is_mention=False,
                timestamp=event_ts,
                platform_context={
                    "reply_token": event.reply_token,
                    "message_id": event.message.id,
                    "received_at": received_at.isoformat(),
                },
            )
            messages.append(msg)

    return messages
