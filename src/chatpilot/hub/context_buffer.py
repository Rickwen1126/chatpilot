"""Context buffer — per-route sliding window of group chat messages."""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from pathlib import Path

from chatpilot.core.types import ContextMessage

logger = logging.getLogger(__name__)


class ContextBuffer:
    """In-memory context buffer with disk flush capability."""

    def __init__(self, default_window: int = 20, data_dir: Path | None = None) -> None:
        self._buffers: dict[str, list[ContextMessage]] = defaultdict(list)
        self._window_sizes: dict[str, int] = {}
        self._default_window = default_window
        self._data_dir = data_dir or Path("data/context")

    def set_window_size(self, route_id: str, size: int) -> None:
        self._window_sizes[route_id] = size

    def _get_window(self, route_id: str) -> int:
        return self._window_sizes.get(route_id, self._default_window)

    def append(self, route_id: str, ctx_msg: ContextMessage) -> None:
        """Append a message to the buffer (sliding window auto-evicts old)."""
        buf = self._buffers[route_id]
        buf.append(ctx_msg)
        window = self._get_window(route_id)
        if len(buf) > window:
            self._buffers[route_id] = buf[-window:]

    def drain(self, route_id: str) -> list[ContextMessage]:
        """Take all messages from buffer and clear it."""
        messages = self._buffers.pop(route_id, [])
        return messages

    def count(self, route_id: str) -> int:
        """Return number of messages in buffer."""
        c = len(self._buffers.get(route_id, []))
        return c

    def peek(self, route_id: str) -> list[ContextMessage]:
        """View buffer contents without clearing."""
        return list(self._buffers.get(route_id, []))

    def format_context(self, messages: list[ContextMessage]) -> str:
        """Format buffer messages into structured context prefix.

        Format per research.md R-008:
        [群組近期對話]
        [背景] UserA (14:30): text
        [busy 期間] UserB (14:31): text
        ---
        [以下是直接對你說的訊息]
        """
        if not messages:
            return ""
        lines = ["[群組近期對話]"]
        for msg in messages:
            ts = msg.timestamp.strftime("%H:%M")
            lines.append(f"[背景] {msg.user_name} ({ts}): {msg.text}")
        lines.append("---")
        lines.append("[以下是直接對你說的訊息]")
        return "\n".join(lines)

    async def flush_to_disk(self, route_id: str) -> None:
        """Write current buffer to disk as JSON (cold layer)."""
        messages = self.peek(route_id)
        if not messages:
            return
        route_dir = self._data_dir / route_id
        route_dir.mkdir(parents=True, exist_ok=True)
        data = [msg.model_dump(mode="json") for msg in messages]
        path = route_dir / "context.json"
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.debug("Flushed %d context messages to %s", len(data), path)
