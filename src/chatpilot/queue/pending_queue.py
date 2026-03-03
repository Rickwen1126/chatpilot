"""Pending message queue — in-memory queue for timeout-deferred responses."""

from __future__ import annotations

import time

from chatpilot.core.types import PendingMessage


class PendingQueue:
    """In-memory pending message queue keyed by session_id."""

    def __init__(self) -> None:
        self._store: dict[str, list[PendingMessage]] = {}

    def enqueue(self, session_id: str, content: str, ttl_ms: int = 1_800_000) -> None:
        entry = PendingMessage(
            session_id=session_id,
            content=content,
            enqueued_at=int(time.time() * 1000),
            ttl_ms=ttl_ms,
        )
        self._store.setdefault(session_id, []).append(entry)

    def dequeue(self, session_id: str) -> PendingMessage | None:
        entries = self._store.get(session_id)
        if not entries:
            return None
        now_ms = int(time.time() * 1000)
        # Remove expired entries from the front
        while entries and (now_ms - entries[0].enqueued_at > entries[0].ttl_ms):
            entries.pop(0)
        if not entries:
            del self._store[session_id]
            return None
        return entries.pop(0)

    def cleanup(self) -> None:
        now_ms = int(time.time() * 1000)
        empty_keys: list[str] = []
        for sid, entries in self._store.items():
            self._store[sid] = [
                e for e in entries if now_ms - e.enqueued_at <= e.ttl_ms
            ]
            if not self._store[sid]:
                empty_keys.append(sid)
        for key in empty_keys:
            del self._store[key]


pending_queue = PendingQueue()
