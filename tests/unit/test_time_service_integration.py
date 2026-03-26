"""Integration tests — verify TimeService is correctly wired into subsystems.

These tests verify that cron, reminder, observer, context_buffer,
and memory store all use TimeService instead of scattered datetime calls.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from chatpilot.core.time_service import TimeService
from chatpilot.core.types import ContextMessage, ContextMessageType
from chatpilot.hub.context_buffer import ContextBuffer
from chatpilot.memory.store import SqliteMemoryStore
from chatpilot.memory.types import MemoryStatus


@pytest.fixture(autouse=True)
def _init_time_service():
    """Ensure TimeService is initialized for all tests."""
    TimeService.init("Asia/Taipei")
    yield
    TimeService._instance = None


# ── format_context: inject_timestamp ─────────────────────────────


def test_format_context_inject_timestamp_true():
    """inject_timestamp=True → shows local time in parentheses."""
    buf = ContextBuffer()
    # UTC 06:30 → Taipei 14:30
    msg = ContextMessage(
        user_id="u1",
        user_name="Alice",
        text="hello",
        timestamp=datetime(2026, 3, 26, 6, 30, tzinfo=timezone.utc),
        message_type=ContextMessageType.background,
    )
    result = buf.format_context([msg], inject_timestamp=True)
    assert "(14:30)" in result
    assert "Alice" in result


def test_format_context_inject_timestamp_false():
    """inject_timestamp=False → no time shown."""
    buf = ContextBuffer()
    msg = ContextMessage(
        user_id="u1",
        user_name="Alice",
        text="hello",
        timestamp=datetime(2026, 3, 26, 6, 30, tzinfo=timezone.utc),
        message_type=ContextMessageType.background,
    )
    result = buf.format_context([msg], inject_timestamp=False)
    assert "(14:30)" not in result
    assert "Alice" in result
    assert "[背景] Alice: hello" in result


def test_format_context_default_no_timestamp():
    """Default (no inject_timestamp) → no time shown (chatbot mode)."""
    buf = ContextBuffer()
    msg = ContextMessage(
        user_id="u1",
        user_name="Bob",
        text="test",
        timestamp=datetime(2026, 3, 26, 10, 0, tzinfo=timezone.utc),
        message_type=ContextMessageType.background,
    )
    result = buf.format_context([msg])
    # Default = False → no parenthesized time
    assert "(18:00)" not in result
    assert "[背景] Bob: test" in result


# ── Cron parser: default after uses TimeService ──────────────────


def test_cron_parser_default_returns_utc():
    """calculate_next_run with no 'after' uses TimeService.utc_now()."""
    from chatpilot.cron.parser import calculate_next_run

    result = calculate_next_run("daily 12:00")
    assert result.tzinfo == timezone.utc
    # Should be within 24h of now
    now = TimeService.get().utc_now()
    diff = (result - now).total_seconds()
    assert 0 < diff <= 86400


def test_cron_parser_interval_from_time_service():
    """Interval uses TimeService.utc_now() as base."""
    from chatpilot.cron.parser import calculate_next_run

    before = TimeService.get().utc_now()
    result = calculate_next_run("interval 15m")
    after = TimeService.get().utc_now()
    # Should be ~15 minutes after now
    diff = (result - before).total_seconds()
    assert 14 * 60 <= diff <= 15 * 60 + 1


# ── CronScheduler: _tick uses TimeService for due query ──────────


@pytest.fixture
async def store(tmp_path):
    s = SqliteMemoryStore(db_path=str(tmp_path / "test.db"))
    await s.initialize()
    yield s
    await s.close()


async def test_cron_tick_queries_due_via_time_service(store):
    """CronScheduler._tick() uses TimeService.utc_now() to find due items."""
    from chatpilot.cron.scheduler import CronScheduler

    ts = TimeService.get()
    past = (ts.utc_now() - timedelta(minutes=5)).isoformat()
    await store.save("r1", "reminder", {"text": "due now", "due_at": past})

    mock_scheduler = AsyncMock()
    mock_scheduler.enqueue = AsyncMock()

    cron = CronScheduler(
        store, AsyncMock(), task_scheduler=mock_scheduler, tick_interval=60
    )
    await cron._tick()

    # Reminder should be found and enqueued
    mock_scheduler.enqueue.assert_called_once()
    task = mock_scheduler.enqueue.call_args[0][0]
    assert task.pipeline_name == "general-agent"
    assert "due now" in task.input_data["description"]


async def test_cron_tick_skips_future_reminder(store):
    """Future reminder not triggered by _tick()."""
    from chatpilot.cron.scheduler import CronScheduler

    ts = TimeService.get()
    future = (ts.utc_now() + timedelta(hours=2)).isoformat()
    await store.save("r1", "reminder", {"text": "later", "due_at": future})

    mock_scheduler = AsyncMock()
    cron = CronScheduler(
        store, AsyncMock(), task_scheduler=mock_scheduler, tick_interval=60
    )
    await cron._tick()

    mock_scheduler.enqueue.assert_not_called()


async def test_schedule_next_run_is_utc(store):
    """After schedule triggers, next_run_at should still be UTC ISO."""
    from chatpilot.cron.scheduler import CronScheduler

    ts = TimeService.get()
    past = (ts.utc_now() - timedelta(minutes=1)).isoformat()
    await store.save("r1", "schedule", {
        "cron_expr": "daily 08:00",
        "tool_name": "echo",
        "next_run_at": past,
    })

    mock_scheduler = AsyncMock()
    mock_scheduler.enqueue = AsyncMock()
    cron = CronScheduler(
        store, AsyncMock(), task_scheduler=mock_scheduler, tick_interval=60
    )
    await cron._tick()

    # Verify next_run_at was updated
    items = await store.list("r1", "schedule")
    assert len(items) == 1
    next_run = items[0]["next_run_at"]
    # Should be a valid ISO string parseable as UTC
    parsed = datetime.fromisoformat(next_run)
    assert parsed.tzinfo is not None
    assert parsed > ts.utc_now()  # should be in the future


# ── Memory store: created_at is UTC ISO ──────────────────────────


async def test_memory_store_created_at_is_utc(store):
    """Auto-generated created_at should be UTC ISO via TimeService."""
    id = await store.save("r1", "memo", {"text": "check time"})
    item = await store.get("r1", "memo", id)
    created = item["created_at"]
    # Should be a valid ISO string
    parsed = datetime.fromisoformat(created)
    assert parsed.tzinfo is not None
    # Should be close to now
    diff = abs((TimeService.get().utc_now() - parsed).total_seconds())
    assert diff < 5


async def test_observation_query_uses_time_service(store):
    """query_observations uses TimeService for 'since' calculation."""
    ts = TimeService.get()
    # Save an observation with recent batch_time
    recent = ts.utc_now().isoformat()
    await store.save("r1", "observation", {
        "batch_time": recent,
        "message_count": 5,
        "entries": [{"category": "進料", "who": "A", "content": "test"}],
        "summary": "1 筆紀錄",
    })

    # Save an old observation (8 days ago)
    old = (ts.utc_now() - timedelta(days=8)).isoformat()
    await store.save("r1", "observation", {
        "batch_time": old,
        "message_count": 3,
        "entries": [{"category": "出料", "who": "B", "content": "old"}],
        "summary": "1 筆紀錄",
    })

    # Query last 7 days — should only get the recent one
    results = await store.query_observations("r1", days=7)
    assert len(results) == 1
    assert results[0]["entries"][0]["category"] == "進料"


# ── TimeService.today() matches local date ───────────────────────


def test_today_is_local_not_utc():
    """TimeService.today() returns local date, not UTC date.

    This is critical for observer batch: record_date must be local.
    When UTC is 23:00 March 25 → Taipei is 07:00 March 26.
    """
    ts = TimeService("Asia/Taipei")
    utc_late = datetime(2026, 3, 25, 23, 0, tzinfo=timezone.utc)
    # Taipei: March 26 07:00
    local = ts.to_local(utc_late)
    assert local.date().day == 26
    assert local.strftime("%Y-%m-%d") == "2026-03-26"


def test_format_time_converts_utc_to_local():
    """format_time must convert UTC to local before formatting.

    Observer context: UTC 02:00 → Taipei 10:00.
    """
    ts = TimeService("Asia/Taipei")
    utc = datetime(2026, 3, 26, 2, 0, tzinfo=timezone.utc)
    assert ts.format_time(utc) == "10:00"


# ── from_epoch_ms: LINE timestamp ────────────────────────────────


def test_from_epoch_ms_line_timestamp():
    """LINE event.timestamp (epoch ms) → correct UTC datetime."""
    ts = TimeService("Asia/Taipei")
    # 2026-03-26 10:00:00 UTC = 1774519200000 ms
    epoch_ms = 1774519200000
    dt = ts.from_epoch_ms(epoch_ms)
    assert dt.tzinfo == timezone.utc
    assert dt.year == 2026
    assert dt.month == 3
    assert dt.day == 26
    assert dt.hour == 10


def test_from_epoch_ms_to_local():
    """LINE epoch ms → UTC → local display should be correct."""
    ts = TimeService("Asia/Taipei")
    # UTC 10:00 → Taipei 18:00
    epoch_ms = 1774519200000
    dt = ts.from_epoch_ms(epoch_ms)
    assert ts.format_time(dt) == "18:00"
