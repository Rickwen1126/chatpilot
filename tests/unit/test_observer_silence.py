"""Observer silence tests — verify observer NEVER responds to the group.

業主強烈要求：群組的人不能發現有 bot 存在。
These tests cover every possible leak path.
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from chatpilot.core.types import (
    ContextMessageType,
    Message,
    Response,
)
from chatpilot.hub.context_buffer import ContextBuffer
from chatpilot.hub.hub import InMemoryMessageHub


def _make_hub(observer_route: str = "line:Uobs123") -> tuple[
    InMemoryMessageHub, AsyncMock, AsyncMock
]:
    """Create hub with observer registered + mock callbacks."""
    adapter = AsyncMock()
    adapter.send_reply = AsyncMock()
    adapter.push_message = AsyncMock()
    adapter.format_hint = None

    on_proceed = AsyncMock()

    hub = InMemoryMessageHub(
        context_buffer=ContextBuffer(),
        adapters={"line": adapter, "mock": adapter},
        on_proceed=on_proceed,
    )
    hub.register_observer(observer_route, batch_size=10, categories=["請假"])
    return hub, adapter, on_proceed


def _msg(
    text="hello",
    user_id="Uobs123",
    platform="line",
    group_id=None,
    is_mention=False,
) -> Message:
    return Message(
        text=text,
        user_id=user_id,
        user_name="TestUser",
        platform=platform,
        group_id=group_id,
        conversation_id=group_id or user_id,
        is_mention=is_mention,
        timestamp=datetime(2026, 3, 26, 10, 0, tzinfo=timezone.utc),
    )


# ── Core: observer silently buffers ──────────────────────────────


async def test_observer_normal_message_no_reply():
    """Normal message → buffer only, no reply."""
    hub, adapter, on_proceed = _make_hub()
    msg = _msg("今天天氣好熱")
    await hub.receive(msg, adapter)

    adapter.send_reply.assert_not_called()
    adapter.push_message.assert_not_called()
    on_proceed.assert_not_called()


async def test_observer_mention_no_reply():
    """@mention in observer group → still silent."""
    hub, adapter, on_proceed = _make_hub()
    msg = _msg("@bot 你好", is_mention=True)
    await hub.receive(msg, adapter)

    adapter.send_reply.assert_not_called()
    adapter.push_message.assert_not_called()
    on_proceed.assert_not_called()


async def test_observer_command_no_reply():
    """'/chatbot list' in observer group → still silent."""
    hub, adapter, on_proceed = _make_hub()
    hub.set_on_command(AsyncMock())
    msg = _msg("/chatbot list", is_mention=True)
    await hub.receive(msg, adapter)

    adapter.send_reply.assert_not_called()
    adapter.push_message.assert_not_called()


async def test_observer_media_no_reply():
    """Image message in observer group → still silent."""
    hub, adapter, on_proceed = _make_hub()
    msg = _msg("[圖片 ref:line:msg123]", is_mention=True)
    await hub.receive(msg, adapter)

    adapter.send_reply.assert_not_called()
    adapter.push_message.assert_not_called()


async def test_observer_keyword_trigger_no_reply():
    """Global keyword 'bot' in observer group → still silent."""
    from chatpilot.hub.mention_filter import configure

    configure(["bot"])
    hub, adapter, on_proceed = _make_hub()
    msg = _msg("bot 查庫存", group_id="Uobs123")
    await hub.receive(msg, adapter)

    adapter.send_reply.assert_not_called()
    adapter.push_message.assert_not_called()
    on_proceed.assert_not_called()
    configure([])  # cleanup


async def test_observer_auto_trigger_no_reply():
    """Auto-trigger keyword in observer group → still silent."""
    from chatpilot.hub.mention_filter import configure_auto_triggers

    configure_auto_triggers({"shinyipaint-observer": ["龍泰", "303"]})

    hub, adapter, on_proceed = _make_hub()
    # Even with matching keyword, observer returns early
    msg = _msg("龍泰303有貨嗎", group_id="Uobs123")
    await hub.receive(msg, adapter)

    adapter.send_reply.assert_not_called()
    adapter.push_message.assert_not_called()
    on_proceed.assert_not_called()
    configure_auto_triggers({})  # cleanup


async def test_observer_busy_no_reply():
    """Even if somehow busy, observer NEVER sends '處理中'."""
    hub, adapter, on_proceed = _make_hub()
    hub.set_busy("line:Uobs123")

    msg = _msg("test while busy", is_mention=True)
    await hub.receive(msg, adapter)

    # No "處理中" reply
    adapter.send_reply.assert_not_called()
    adapter.push_message.assert_not_called()


# ── Defense-in-depth: push() and receive_pipeline_result() ───────


async def test_send_reply_blocked_for_observer():
    """hub.send_reply() to observer route → blocked."""
    hub, adapter, _ = _make_hub()
    msg = _msg("test", is_mention=True)
    await hub.send_reply(msg, Response(text="should not send"), adapter)

    adapter.send_reply.assert_not_called()


async def test_push_blocked_for_observer():
    """hub.push() to observer route → blocked, not delivered."""
    hub, adapter, _ = _make_hub()
    await hub.push("line:Uobs123", Response(text="this should not be sent"))

    adapter.push_message.assert_not_called()


async def test_pipeline_result_blocked_for_observer():
    """Pipeline result to observer route → blocked."""
    hub, adapter, _ = _make_hub()
    await hub.receive_pipeline_result(
        "line:Uobs123", "task completed result"
    )

    adapter.push_message.assert_not_called()
    adapter.send_reply.assert_not_called()


# ── Batch: only writes to DB, never to group ─────────────────────


async def test_observer_batch_no_push():
    """When batch triggers, only calls batch callback — never pushes."""
    hub, adapter, _ = _make_hub("line:Uobs123")
    batch_callback = AsyncMock()
    hub._on_observer_batch = batch_callback

    # Send 10 messages to trigger batch
    for i in range(10):
        msg = _msg(f"message {i}")
        await hub.receive(msg, adapter)

    # Wait for background task
    await asyncio.sleep(0.1)

    # Batch callback was called
    batch_callback.assert_called_once()

    # But NO message sent to group
    adapter.send_reply.assert_not_called()
    adapter.push_message.assert_not_called()


async def test_observer_batch_failure_no_push():
    """If batch callback fails, error stays in log — never pushed to group."""
    hub, adapter, _ = _make_hub("line:Uobs123")
    hub._on_observer_batch = AsyncMock(side_effect=Exception("LLM timeout"))

    for i in range(10):
        msg = _msg(f"message {i}")
        await hub.receive(msg, adapter)

    await asyncio.sleep(0.1)

    # Error swallowed, NOT pushed to group
    adapter.send_reply.assert_not_called()
    adapter.push_message.assert_not_called()


# ── Cross-platform: observer registered for all adapters ─────────


async def test_observer_blocks_all_platforms():
    """Observer registered for line: and mock: — both silent."""
    hub, adapter, on_proceed = _make_hub("line:Uobs123")
    # Server also registers mock:Uobs123
    hub.register_observer("mock:Uobs123", batch_size=10, categories=[])

    # LINE message
    msg_line = _msg("test from LINE", platform="line")
    await hub.receive(msg_line, adapter)

    # Mock message
    msg_mock = _msg("test from mock", platform="mock", user_id="Uobs123")
    await hub.receive(msg_mock, adapter)

    adapter.send_reply.assert_not_called()
    adapter.push_message.assert_not_called()
    on_proceed.assert_not_called()


# ── Non-observer route still works normally ──────────────────────


async def test_non_observer_route_responds():
    """Sanity check: non-observer private chat still gets response."""
    hub, adapter, on_proceed = _make_hub("line:Uobs123")

    # Different user, not observer
    msg = _msg("hello", user_id="Uother", platform="line")
    await hub.receive(msg, adapter)
    await asyncio.sleep(0.1)  # wait for background task

    # Should proceed to chatbot
    on_proceed.assert_called_once()
