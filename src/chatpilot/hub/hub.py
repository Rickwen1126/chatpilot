"""InMemoryMessageHub — implements MessageHub Protocol."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Callable, Coroutine, Literal

from chatpilot.adapters.protocol import ChannelAdapter
from chatpilot.core.types import (
    ContextMessage,
    ContextMessageType,
    Message,
    Response,
)
from chatpilot.hub.context_buffer import ContextBuffer
from chatpilot.hub.mention_filter import is_mention

logger = logging.getLogger(__name__)

# Pattern: message text is ONLY media refs (image/audio/file), no other content
_MEDIA_REF_PATTERN = re.compile(
    r"^(\[(圖片|音檔|檔案|影片)\s+ref:[^\]]+\]\s*)+$"
)


def _is_media_only(text: str) -> bool:
    """Check if message text contains only media refs with no other content."""
    return bool(_MEDIA_REF_PATTERN.match(text.strip()))

OnProceedCallback = Callable[
    [Message, str | None, ChannelAdapter], Coroutine[Any, Any, None]
]
OnCommandCallback = Callable[
    [str, str, Message, ChannelAdapter], Coroutine[Any, Any, None]
]
OnPipelineResultCallback = Callable[
    [str, str], Coroutine[Any, Any, None]
]


class InMemoryMessageHub:
    """In-memory message hub with busy/idle gating and context buffer."""

    def __init__(
        self,
        context_buffer: ContextBuffer,
        adapters: dict[str, ChannelAdapter],
        on_proceed: OnProceedCallback | None = None,
        on_command: OnCommandCallback | None = None,
        on_pipeline_result: OnPipelineResultCallback | None = None,
    ) -> None:
        self._context_buffer = context_buffer
        self._adapters = adapters
        self._busy: dict[str, bool] = {}
        self._on_proceed = on_proceed
        self._on_command = on_command
        self._on_pipeline_result = on_pipeline_result
        self._pipeline_result_queue: dict[str, list[str]] = {}
        self._background_tasks: set[asyncio.Task] = set()

    def set_on_proceed(self, callback: OnProceedCallback) -> None:
        self._on_proceed = callback

    def set_on_command(self, callback: OnCommandCallback) -> None:
        self._on_command = callback

    def set_on_pipeline_result(self, callback: OnPipelineResultCallback) -> None:
        self._on_pipeline_result = callback

    async def receive(self, message: Message, adapter: ChannelAdapter) -> None:
        """Process inbound message through mention filter + busy/idle gate."""
        route_id = f"{message.platform}:{message.conversation_id}"

        mentioned = is_mention(message)

        # Check prefix commands (group requires mention, private chat always)
        # Strip leading @mention or keyword: "@Bot /chatbot" or "bot /chatbot" → "/chatbot"
        text = message.text.strip()
        if mentioned and not text.startswith("/"):
            text = re.sub(r"^@\S+\s+", "", text)  # strip @Bot
            if not text.startswith("/"):
                text = re.sub(r"^\S+\s+", "", text, count=1)  # strip keyword (e.g. "bot ")
        if text.startswith("/") and mentioned:
            cmd_parts = text.split(maxsplit=1)
            command = cmd_parts[0][1:]
            args = cmd_parts[1] if len(cmd_parts) > 1 else ""
            if self._on_command:
                await self._on_command(command, args, message, adapter)
            return

        # Media-only message (image/audio/file ref without other text):
        # buffer silently, even in private chat — user will follow up with text
        if mentioned and _is_media_only(message.text):
            self._context_buffer.append(
                route_id,
                ContextMessage(
                    user_id=message.user_id,
                    user_name=message.user_name or message.user_id,
                    text=message.text,
                    timestamp=message.timestamp,
                    message_type=ContextMessageType.background,
                ),
            )
            logger.debug("Media-only message buffered for %s", route_id)
            return

        if not mentioned:
            # Group non-mention: store in context buffer silently
            self._context_buffer.append(
                route_id,
                ContextMessage(
                    user_id=message.user_id,
                    user_name=message.user_name or message.user_id,
                    text=message.text,
                    timestamp=message.timestamp,
                    message_type=ContextMessageType.background,
                ),
            )
            return

        # Mentioned or private chat, but bot is busy — reject, don't buffer
        if self.get_status(route_id) == "busy":
            try:
                await adapter.send_reply(message, Response(text="處理中，請稍候…"))
            except Exception:
                logger.warning("Failed to send busy reply for %s", route_id)
            return

        # Idle + mentioned: drain context buffer and proceed
        context_messages = self._context_buffer.drain(route_id)
        context_prefix = self._context_buffer.format_context(context_messages) or None

        if self._on_proceed:
            self.set_busy(route_id)  # MUST set before create_task to prevent race
            task = asyncio.create_task(
                self._process_and_reply(route_id, message, context_prefix, adapter)
            )
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)

    async def _process_and_reply(
        self,
        route_id: str,
        message: Message,
        context_prefix: str | None,
        adapter: ChannelAdapter,
    ) -> None:
        """Run on_proceed callback, then set idle. Caller MUST set_busy first."""
        try:
            await self._on_proceed(message, context_prefix, adapter)
        except Exception:
            logger.exception("Error processing message for %s", route_id)
        finally:
            self.set_idle(route_id)

    async def send_reply(
        self, message: Message, response: Response, adapter: ChannelAdapter
    ) -> None:
        await adapter.send_reply(message, response)

    async def push(self, route_id: str, response: Response) -> None:
        """Push async result back to the originating conversation."""
        platform = route_id.split(":")[0]
        adapter = self._adapters.get(platform)
        if adapter is None:
            logger.error("No adapter for platform '%s'", platform)
            return
        try:
            await adapter.push_message(route_id, response)
        except Exception:
            logger.exception("Push failed for %s", route_id)

    async def receive_pipeline_result(
        self, route_id: str, result: str, reply_mode: str = "direct"
    ) -> None:
        """Pipeline result entry — never discarded."""
        if reply_mode == "direct" or self._on_pipeline_result is None:
            await self.push(route_id, Response(text=result))
            return
        # via_chatbot: busy → queue; idle → process through chatbot
        if self.get_status(route_id) == "busy":
            self._pipeline_result_queue.setdefault(route_id, []).append(result)
            logger.info(
                "Queued pipeline result for %s (queue=%d)",
                route_id, len(self._pipeline_result_queue[route_id]),
            )
            return
        self.set_busy(route_id)
        try:
            await self._on_pipeline_result(route_id, result)
        except Exception:
            logger.exception("Pipeline result processing failed for %s", route_id)
            # Fallback: push raw result
            await self.push(route_id, Response(text=result))
        finally:
            self.set_idle(route_id)

    def get_status(self, route_id: str) -> Literal["idle", "busy"]:
        return "busy" if self._busy.get(route_id, False) else "idle"

    def set_busy(self, route_id: str) -> None:
        self._busy[route_id] = True

    def set_idle(self, route_id: str) -> None:
        self._busy[route_id] = False
        # Drain queued pipeline results
        queue = self._pipeline_result_queue.get(route_id, [])
        if queue and self._on_pipeline_result is not None:
            task = asyncio.create_task(self._drain_pipeline_results(route_id))
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)

    async def _drain_pipeline_results(self, route_id: str) -> None:
        """Process queued pipeline results sequentially."""
        while True:
            queue = self._pipeline_result_queue.get(route_id, [])
            if not queue:
                break
            result = queue.pop(0)
            self._busy[route_id] = True
            try:
                await self._on_pipeline_result(route_id, result)
            except Exception:
                logger.exception(
                    "Drain pipeline result failed for %s", route_id
                )
                try:
                    await self.push(route_id, Response(text=result))
                except Exception:
                    logger.exception("Fallback push also failed for %s", route_id)
            finally:
                self._busy[route_id] = False
