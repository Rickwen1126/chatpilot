"""LINE channel adapter — implements ChannelAdapter Protocol."""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os

from linebot.v3 import WebhookParser
from linebot.v3.messaging import (
    ApiClient,
    Configuration,
    MessagingApi,
    ReplyMessageRequest,
    TextMessage,
)

from chatpilot.channels.line.parser import parse_line_events
from chatpilot.core.errors import AdapterError
from chatpilot.core.types import LinePlatformContext, Message, Response

logger = logging.getLogger(__name__)

LINE_MAX_TEXT_LENGTH = 5000
TRUNCATION_SUFFIX = "…（訊息過長，已截斷）"


class LineAdapter:
    """LINE Messaging API adapter."""

    def __init__(self) -> None:
        self._secret: str = ""
        self._parser: WebhookParser | None = None
        self._api: MessagingApi | None = None

    @property
    def platform(self) -> str:
        return "line"

    def initialize(self) -> None:
        """Initialize with env vars. Called at server startup."""
        self._secret = os.environ.get("LINE_CHANNEL_SECRET", "")
        token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
        self._parser = WebhookParser(self._secret)
        config = Configuration(access_token=token)
        api_client = ApiClient(config)
        self._api = MessagingApi(api_client)

    def verify_signature(self, raw_body: bytes, signature: str) -> bool:
        try:
            gen_signature = hmac.new(
                self._secret.encode("utf-8"),
                raw_body,
                hashlib.sha256,
            ).digest()
            return hmac.compare_digest(
                signature.encode("utf-8"),
                base64.b64encode(gen_signature).decode("utf-8").encode("utf-8"),
            )
        except Exception:
            return False

    def parse_messages(self, raw_body: bytes) -> list[Message]:
        # Requires signature; use parse_messages_with_signature
        return []

    def parse_messages_with_signature(
        self, raw_body: bytes, signature: str
    ) -> list[Message]:
        """Parse messages with the signature (used by webhook handler)."""
        if self._parser is None:
            return []
        try:
            events = self._parser.parse(raw_body.decode("utf-8"), signature)
            return parse_line_events(raw_body, events)
        except Exception as e:
            logger.error("LINE parse error: %s", e)
            return []

    async def send_response(self, message: Message, response: Response) -> None:
        ctx = message.platform_context
        if not isinstance(ctx, LinePlatformContext):
            raise AdapterError("Missing LINE platform context")
        text = response.text
        if len(text) > LINE_MAX_TEXT_LENGTH:
            text = (
                text[: LINE_MAX_TEXT_LENGTH - len(TRUNCATION_SUFFIX)]
                + TRUNCATION_SUFFIX
            )
        try:
            if self._api is None:
                raise AdapterError("LINE API not initialized")
            self._api.reply_message(
                ReplyMessageRequest(
                    reply_token=ctx.reply_token,
                    messages=[TextMessage(text=text)],
                )
            )
        except AdapterError:
            raise
        except Exception as e:
            raise AdapterError("LINE reply failed", cause=e) from e

    async def send_processing_ack(self, message: Message) -> None:
        ctx = message.platform_context
        if not isinstance(ctx, LinePlatformContext):
            return
        try:
            if self._api is None:
                return
            self._api.reply_message(
                ReplyMessageRequest(
                    reply_token=ctx.reply_token,
                    messages=[TextMessage(text="處理中，請稍候…")],
                )
            )
        except Exception as e:
            logger.warning("Failed to send processing ACK: %s", e)


line_adapter = LineAdapter()
