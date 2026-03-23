"""ImageInjector — bridges tool image output to response attachments.

Independent of both tool modules and adapter/hub modules.
Tools add pending images, on_proceed pops them into Response.attachments.
"""

from __future__ import annotations


class ImageInjector:
    """Manages pending image URLs between tool execution and response."""

    def __init__(self) -> None:
        self._pending: dict[str, list[str]] = {}

    def add(self, session_id: str, url: str) -> None:
        """Tool calls this to queue an image for the response."""
        self._pending.setdefault(session_id, []).append(url)

    def pop(self, session_id: str) -> list[str]:
        """on_proceed calls this to get + clear pending images."""
        return self._pending.pop(session_id, [])
