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


async def test_reminder_push(store, mock_hub):
    """Due reminder should be pushed and marked completed."""
    past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    await store.save("r1", "reminder", {"text": "開會", "due_at": past})

    scheduler = CronScheduler(store, mock_hub, tick_interval=60)
    await scheduler._tick()

    # Hub push was called
    mock_hub.push.assert_called_once()
    call_args = mock_hub.push.call_args
    assert call_args[0][0] == "r1"
    assert "開會" in call_args[0][1].text

    # Reminder marked completed
    items = await store.list("r1", "reminder")
    assert items[0]["status"] == MemoryStatus.completed.value


async def test_reminder_not_due(store, mock_hub):
    """Future reminder should not be triggered."""
    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    await store.save("r1", "reminder", {"text": "later", "due_at": future})

    scheduler = CronScheduler(store, mock_hub, tick_interval=60)
    await scheduler._tick()

    mock_hub.push.assert_not_called()


async def test_reminder_push_failure(store, mock_hub):
    """Failed push should mark reminder as failed with error."""
    past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    await store.save("r1", "reminder", {"text": "fail", "due_at": past})

    mock_hub.push.side_effect = Exception("push failed")

    scheduler = CronScheduler(store, mock_hub, tick_interval=60)
    await scheduler._tick()

    items = await store.list("r1", "reminder")
    assert items[0]["status"] == MemoryStatus.failed.value
    assert "push failed" in items[0]["last_error"]
