from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock

from chatpilot.core.types import Message
from chatpilot.hub.context_buffer import ContextBuffer
from chatpilot.hub.hub import InMemoryMessageHub


def _msg(
    *,
    text: str,
    group_id: str = "C123",
    is_mention: bool = False,
) -> Message:
    return Message(
        text=text,
        user_id="Uworker",
        user_name="Worker",
        platform="line",
        group_id=group_id,
        conversation_id=group_id,
        is_mention=is_mention,
        timestamp=datetime(2026, 4, 6, 10, 0, tzinfo=timezone.utc),
    )


def _make_hub() -> tuple[InMemoryMessageHub, AsyncMock, AsyncMock]:
    adapter = AsyncMock()
    adapter.send_reply = AsyncMock()
    adapter.push_message = AsyncMock()
    adapter.format_hint = None
    on_proceed = AsyncMock()

    hub = InMemoryMessageHub(
        context_buffer=ContextBuffer(),
        adapters={"line": adapter},
        on_proceed=on_proceed,
    )
    hub.register_route_policy(
        "line:C123",
        reply_policy="addressed",
        processing_policy="interactive",
        capture_enabled=True,
    )
    hub.register_capture("line:C123", batch_size=10, categories=["請假"])
    return hub, adapter, on_proceed


async def test_non_addressed_group_message_still_captures() -> None:
    hub, adapter, on_proceed = _make_hub()

    await hub.receive(_msg(text="今天下午水泥漆到了"), adapter)

    on_proceed.assert_not_called()
    adapter.send_reply.assert_not_called()
    assert hub._observation_buffer.count("line:C123") == 1
    assert hub._context_buffer.count("line:C123") == 1


async def test_addressed_group_message_fans_out_to_capture_and_reply() -> None:
    hub, adapter, on_proceed = _make_hub()

    await hub.receive(_msg(text="@bot 今天進了什麼料", is_mention=True), adapter)
    await asyncio.sleep(0.1)

    on_proceed.assert_called_once()
    adapter.send_reply.assert_not_called()
    assert hub._observation_buffer.count("line:C123") == 1
    assert hub._context_buffer.count("line:C123") == 0
