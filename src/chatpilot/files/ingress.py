"""Ingress preprocessor placeholder for file registration/prefetch."""

from __future__ import annotations

import logging

from chatpilot.adapters.protocol import ChannelAdapter
from chatpilot.core.types import Message
from chatpilot.files.center import FileHandleCenter
from chatpilot.files.policy import IngressAction, decide_ingress_action

logger = logging.getLogger(__name__)


class InboundFilePreprocessor:
    """Message ingress hook for canonical file registration.

    Phase 1/2 only establishes the service boundary. Actual message enrichment
    lands in the next milestone once adapter emitters and hub integration are
    wired in.
    """

    def __init__(self, center: FileHandleCenter) -> None:
        self._center = center

    async def process(
        self,
        message: Message,
        adapter: ChannelAdapter,
    ) -> Message:
        _ = adapter
        if not message.source_handles:
            return message

        registered = list(message.file_handles)
        file_ids = list(message.platform_context.get("file_ids", []))

        for source in message.source_handles:
            handle = await self._center.register(source)
            registered.append(handle)
            file_ids.append(handle.file_id)

            action = decide_ingress_action(source)
            logger.info(
                "[file] ingress route=%s locator=%s kind=%s action=%s file_id=%s",
                source.route_id,
                source.native_locator,
                source.kind.value,
                action.value,
                handle.file_id,
            )
            if action == IngressAction.download_now:
                await self._center.download_now(handle.file_id)
            elif action == IngressAction.prefetch:
                await self._center.prefetch(handle.file_id)

        message.file_handles = registered
        message.platform_context["file_ids"] = file_ids
        return message
