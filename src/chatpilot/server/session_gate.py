"""Session gate — prevents concurrent message processing per session."""

from __future__ import annotations


class SessionGate:
    """In-memory gate that allows only one message per session at a time.

    When a session is busy, new messages are queued (only the latest is kept).
    On release, the queued message text is returned so the caller can notify
    the user that it was dropped.
    """

    def __init__(self) -> None:
        self._busy: dict[str, bool] = {}
        self._queued: dict[str, str] = {}

    def is_busy(self, session_id: str) -> bool:
        return self._busy.get(session_id, False)

    def acquire(self, session_id: str) -> None:
        self._busy[session_id] = True

    def release(self, session_id: str) -> str | None:
        """Release the gate. Returns the dropped message text if any."""
        self._busy.pop(session_id, None)
        return self._queued.pop(session_id, None)

    def queue(self, session_id: str, text: str) -> None:
        """Store the latest queued message (overwrites previous)."""
        self._queued[session_id] = text


session_gate = SessionGate()
