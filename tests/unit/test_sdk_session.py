"""Unit tests for SdkSession attachment forwarding."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from chatpilot.sdk.session import SdkSession


class _FakeRawSession:
    def __init__(self) -> None:
        self.calls: list[tuple[dict, float]] = []

    def on(self, handler) -> None:
        return None

    async def send_and_wait(self, options: dict, timeout: float | None = None):
        self.calls.append((options, timeout or 0.0))
        return SimpleNamespace(data=SimpleNamespace(content="ok"))

    async def destroy(self) -> None:
        return None


@pytest.mark.asyncio
async def test_sdk_session_forwards_attachments():
    raw = _FakeRawSession()
    session = SdkSession(raw, "sid-1")

    result = await session.send_and_wait_with_attachments(
        "看圖",
        attachments=[{"type": "file", "path": "/tmp/image.jpg"}],
        timeout=30.0,
    )

    assert result == "ok"
    assert raw.calls == [
        (
            {
                "prompt": "看圖",
                "attachments": [{"type": "file", "path": "/tmp/image.jpg"}],
            },
            30.0,
        )
    ]
