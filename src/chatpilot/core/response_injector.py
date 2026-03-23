"""ResponseInjector — bridges tool structured output to response.

Independent of both tool modules and adapter/hub modules.
Tools add pending items (images, links, files), on_proceed pops
them and injects into the final Response.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class InjectedItem:
    type: str  # "image" | "link" | "file"
    data: str  # URL or text


class ResponseInjector:
    """Manages pending response items between tool execution and response."""

    def __init__(self) -> None:
        self._pending: dict[str, list[InjectedItem]] = {}

    def add(self, session_id: str, type: str, data: str) -> None:
        """Tool calls this to queue an item for the response."""
        self._pending.setdefault(session_id, []).append(
            InjectedItem(type=type, data=data)
        )

    def pop(self, session_id: str) -> list[InjectedItem]:
        """on_proceed calls this to get + clear pending items."""
        return self._pending.pop(session_id, [])
