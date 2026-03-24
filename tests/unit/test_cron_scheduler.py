"""Tests for CronScheduler."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from chatpilot.cron.scheduler import CronScheduler
from chatpilot.memory.store import SqliteMemoryStore
from chatpilot.memory.types import MemoryStatus


@pytest.fixture
async def store(tmp_path):
    s = SqliteMemoryStore(db_path=str(tmp_path / "test.db"))
    await s.initialize()
    yield s
    await s.close()


@pytest.fixture
def mock_hub():
    hub = AsyncMock()
    hub.push = AsyncMock()
    return hub


@pytest.fixture
def mock_task_scheduler():
    scheduler = AsyncMock()
    scheduler.enqueue = AsyncMock()
    return scheduler


async def test_reminder_enqueues_general_agent(store, mock_hub, mock_task_scheduler):
    """Due reminder should enqueue a general-agent task and be marked completed."""
    past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    await store.save("r1", "reminder", {"text": "開會", "due_at": past})

    scheduler = CronScheduler(
        store, mock_hub, task_scheduler=mock_task_scheduler, tick_interval=60
    )
    await scheduler._tick()

    # Task enqueued (not direct push)
    mock_task_scheduler.enqueue.assert_called_once()
    task = mock_task_scheduler.enqueue.call_args[0][0]
    assert task.pipeline_name == "general-agent"
    assert "開會" in task.input_data.get("description", "")
    assert task.chat_route_id == "r1"

    # Reminder marked completed
    items = await store.list("r1", "reminder")
    assert items[0]["status"] == MemoryStatus.completed.value


async def test_reminder_not_due(store, mock_hub, mock_task_scheduler):
    """Future reminder should not be triggered."""
    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    await store.save("r1", "reminder", {"text": "later", "due_at": future})

    scheduler = CronScheduler(
        store, mock_hub, task_scheduler=mock_task_scheduler, tick_interval=60
    )
    await scheduler._tick()

    mock_task_scheduler.enqueue.assert_not_called()


async def test_reminder_no_scheduler_fails(store, mock_hub):
    """Reminder without task_scheduler should fail gracefully."""
    past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    await store.save("r1", "reminder", {"text": "fail", "due_at": past})

    scheduler = CronScheduler(store, mock_hub, tick_interval=60)
    await scheduler._tick()

    items = await store.list("r1", "reminder")
    assert items[0]["status"] == MemoryStatus.failed.value
    assert "task_scheduler" in items[0]["last_error"]


async def test_schedule_uses_tool_name(store, mock_hub, mock_task_scheduler):
    """Schedule should use tool_name field."""
    past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    await store.save("r1", "schedule", {
        "cron_expr": "daily 08:00",
        "tool_name": "echo",
        "next_run_at": past,
    })

    scheduler = CronScheduler(
        store, mock_hub, task_scheduler=mock_task_scheduler, tick_interval=60
    )
    await scheduler._tick()

    mock_task_scheduler.enqueue.assert_called_once()
    task = mock_task_scheduler.enqueue.call_args[0][0]
    assert task.pipeline_name == "echo"
