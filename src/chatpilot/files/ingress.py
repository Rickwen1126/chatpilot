"""Ingress preprocessor placeholder for file registration/prefetch."""

from __future__ import annotations

from chatpilot.adapters.protocol import ChannelAdapter
from chatpilot.core.types import Message
from chatpilot.files.center import FileHandleCenter


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
        _ = (self._center, adapter)
        return message
