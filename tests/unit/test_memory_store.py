"""Tests for SqliteMemoryStore."""

from datetime import datetime, timedelta, timezone

import pytest

from chatpilot.memory.store import SqliteMemoryStore


@pytest.fixture
async def store(tmp_path):
    s = SqliteMemoryStore(db_path=str(tmp_path / "test.db"))
    await s.initialize()
    yield s
    await s.close()


async def test_save_and_get_memo(store):
    id = await store.save("route1", "memo", {"text": "hello"})
    result = await store.get("route1", "memo", id)
    assert result is not None
    assert result["text"] == "hello"
    assert result["route_id"] == "route1"


async def test_list_memos(store):
    await store.save("route1", "memo", {"text": "a"})
    await store.save("route1", "memo", {"text": "b"})
    await store.save("route2", "memo", {"text": "c"})
    items = await store.list("route1", "memo")
    assert len(items) == 2


async def test_delete_memo(store):
    id = await store.save("route1", "memo", {"text": "delete me"})
    assert await store.delete("route1", "memo", id) is True
    assert await store.get("route1", "memo", id) is None
    assert await store.delete("route1", "memo", id) is False


async def test_update_reminder(store):
    id = await store.save("route1", "reminder", {
        "text": "meeting",
        "due_at": datetime.now(timezone.utc).isoformat(),
    })
    await store.update("route1", "reminder", id, {"status": "running"})
    result = await store.get("route1", "reminder", id)
    assert result["status"] == "running"


async def test_query_due_before(store):
    now = datetime.now(timezone.utc)
    past = (now - timedelta(minutes=5)).isoformat()
    future = (now + timedelta(hours=1)).isoformat()

    await store.save("r1", "reminder", {"text": "past", "due_at": past})
    await store.save("r2", "reminder", {"text": "future", "due_at": future})

    due = await store.query_due_before("reminder", now)
    assert len(due) == 1
    assert due[0]["text"] == "past"


async def test_invalid_type(store):
    with pytest.raises(ValueError, match="Unknown memory type"):
        await store.save("r1", "invalid", {"text": "nope"})


async def test_custom_prompt_save_list(store):
    await store.save("r1", "custom_prompt", {"text": "用繁體中文"})
    await store.save("r1", "custom_prompt", {"text": "簡潔回答"})
    items = await store.list("r1", "custom_prompt")
    assert len(items) == 2
