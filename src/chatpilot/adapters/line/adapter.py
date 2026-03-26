"""LINE channel adapter — implements ChannelAdapter Protocol."""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os

from fastapi import Request
from linebot.v3 import WebhookParser
from linebot.v3.messaging import (
    ApiClient,
    Configuration,
    ImageMessage,
    MessagingApi,
    MessagingApiBlob,
    PushMessageRequest,
    ReplyMessageRequest,
    TextMessage,
)

from chatpilot.adapters.line.parser import parse_line_events
from chatpilot.core.errors import AdapterError
from chatpilot.core.time_service import TimeService
from chatpilot.core.types import Message, Response

logger = logging.getLogger(__name__)

LINE_MAX_TEXT_LENGTH = 5000
LINE_MAX_MESSAGES_PER_CALL = 5  # LINE allows up to 5 messages per API call
REPLY_TOKEN_TTL_SECONDS = 25  # LINE reply token expires ~30s, leave 5s buffer


def _build_messages(response: Response) -> list:
    """Build LINE message objects from Response (text + attachments)."""
    msgs = []
    for chunk in _split_text(response.text):
        msgs.append(TextMessage(text=chunk))
    for att in response.attachments:
        if att.type == "image" and att.url:
            msgs.append(ImageMessage(
                original_content_url=att.url,
                preview_image_url=att.url,
            ))
    return msgs


def _split_text(text: str) -> list[str]:
    """Split text into chunks of LINE_MAX_TEXT_LENGTH."""
    if len(text) <= LINE_MAX_TEXT_LENGTH:
        return [text]
    chunks: list[str] = []
    while text:
        chunks.append(text[:LINE_MAX_TEXT_LENGTH])
        text = text[LINE_MAX_TEXT_LENGTH:]
    return chunks


class LineAdapter:
    """LINE Messaging API adapter."""

    def __init__(self) -> None:
        self._secret = os.environ.get("LINE_CHANNEL_SECRET", "")
        token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
        self._parser = WebhookParser(self._secret) if self._secret else None
        if token:
            config = Configuration(access_token=token)
            api_client = ApiClient(config)
            self._api = MessagingApi(api_client)
            self._blob_api = MessagingApiBlob(api_client)
        else:
            self._api = None
            self._blob_api = None

    @property
    def platform(self) -> str:
        return "line"

    @property
    def format_hint(self) -> str:
        return (
            "[格式限制] 此平台不支援 Markdown。"
            "不要使用 **粗體**、`程式碼`、## 標題、[連結](url)。"
            "用純文字、換行、和符號（→、•、★、─）來排版。"
        )

    async def verify_request(self, request: Request) -> bool:
        signature = request.headers.get("X-Line-Signature", "")
        body = await request.body()
        if not signature or not self._secret:
            raise AdapterError("Missing LINE signature", code="SIGNATURE_INVALID")
        try:
            gen_sig = hmac.new(
                self._secret.encode("utf-8"), body, hashlib.sha256
            ).digest()
            valid = hmac.compare_digest(
                signature.encode("utf-8"),
                base64.b64encode(gen_sig).decode("utf-8").encode("utf-8"),
            )
            if not valid:
                raise AdapterError("Invalid LINE signature", code="SIGNATURE_INVALID")
            return True
        except AdapterError:
            raise
        except Exception as e:
            raise AdapterError("Signature verification failed", cause=e) from e

    async def parse_messages(self, request: Request) -> list[Message]:
        if self._parser is None:
            return []
        body = await request.body()
        signature = request.headers.get("X-Line-Signature", "")
        try:
            events = self._parser.parse(body.decode("utf-8"), signature)
            return parse_line_events(events)
        except Exception as e:
            logger.error("LINE parse error: %s", e)
            return []

    async def send_reply(self, message: Message, response: Response) -> None:
        """Reply to a message. Falls back to push if reply token expired or text is long."""
        if self._api is None:
            raise AdapterError("LINE API not initialized")

        msgs = _build_messages(response)
        route_id = f"line:{message.conversation_id}"

        # If expired or too many messages, use push
        # Use received_at (webhook arrival time) not message.timestamp (LINE event time)
        ts = TimeService.get()
        received_at_str = message.platform_context.get("received_at")
        if received_at_str:
            received_at = ts.from_iso(received_at_str)
        else:
            received_at = message.timestamp
        elapsed = ts.elapsed_seconds(received_at)
        if elapsed > REPLY_TOKEN_TTL_SECONDS or len(msgs) > LINE_MAX_MESSAGES_PER_CALL:
            if elapsed > REPLY_TOKEN_TTL_SECONDS:
                logger.info("Reply token expired (%.0fs), using push", elapsed)
            await self.push_message(route_id, response)
            return

        reply_token = message.platform_context.get("reply_token")
        if not reply_token:
            raise AdapterError("Missing reply_token in platform_context")
        try:
            self._api.reply_message(
                ReplyMessageRequest(reply_token=reply_token, messages=msgs)
            )
        except Exception as e:
            logger.warning("Reply failed, falling back to push: %s", e)
            await self.push_message(route_id, response)

    async def push_message(self, route_id: str, response: Response) -> None:
        """Push message to a conversation, splitting long text into chunks."""
        if self._api is None:
            raise AdapterError("LINE API not initialized")
        _, conversation_id = route_id.split(":", 1)
        msgs = _build_messages(response)

        for i in range(0, len(msgs), LINE_MAX_MESSAGES_PER_CALL):
            batch = msgs[i : i + LINE_MAX_MESSAGES_PER_CALL]
            try:
                self._api.push_message(
                    PushMessageRequest(to=conversation_id, messages=batch)
                )
            except Exception as e:
                raise AdapterError("LINE push failed", cause=e) from e

    async def download_media(self, media_id: str) -> bytes | None:
        """Download media from LINE by message ID."""
        if self._blob_api is None:
            return None
        try:
            return self._blob_api.get_message_content(media_id)
        except Exception as e:
            logger.warning("LINE media download failed for %s: %s", media_id, e)
            return None
