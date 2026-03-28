"""Tests for per-route trigger keywords (DB layer + mention_filter cache)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from chatpilot.core.types import Message
from chatpilot.hub.mention_filter import (
    add_route_keyword,
    configure_auto_triggers,
    get_config_keywords,
    get_route_keywords,
    load_route_keywords,
    match_auto_trigger,
    remove_route_keyword,
)
from chatpilot.memory.store import SqliteMemoryStore


def _msg(text: str, platform: str = "line", group_id: str = "Gtest") -> Message:
    return Message(
        text=text,
        user_id="Utest",
        user_name="Tester",
        platform=platform,
        group_id=group_id,
        conversation_id=group_id,
        is_mention=False,
        timestamp=datetime(2026, 3, 28, 10, 0, tzinfo=timezone.utc),
    )


@pytest.fixture(autouse=True)
def _reset_caches():
    """Reset all caches between tests."""
    configure_auto_triggers({})
    load_route_keywords({})
    yield
    configure_auto_triggers({})
    load_route_keywords({})


# ── Config seed works as before ──────────────────────────────────


def test_config_seed_triggers():
    """Config keywords (per-chatbot) trigger match_auto_trigger."""
    configure_auto_triggers({"mybot": ["阿信", "龍泰"]})
    msg = _msg("阿信 查庫存")
    assert match_auto_trigger(msg, "mybot") is True


def test_config_seed_no_match():
    """Non-matching text doesn't trigger."""
    configure_auto_triggers({"mybot": ["阿信"]})
    msg = _msg("阿財 查庫存")
    assert match_auto_trigger(msg, "mybot") is False


# ── DB keywords trigger ──────────────────────────────────────────


def test_db_keyword_triggers():
    """DB keyword (per-route) triggers match_auto_trigger."""
    load_route_keywords({"line:Gtest": ["阿財"]})
    msg = _msg("阿財 查庫存")
    assert match_auto_trigger(msg, "mybot") is True


def test_db_keyword_different_route_no_match():
    """DB keyword for route A doesn't trigger in route B."""
    load_route_keywords({"line:Gother": ["阿財"]})
    msg = _msg("阿財 查庫存", group_id="Gtest")
    assert match_auto_trigger(msg, "mybot") is False


# ── Config + DB union ────────────────────────────────────────────


def test_union_config_and_db():
    """Both config and DB keywords trigger."""
    configure_auto_triggers({"mybot": ["阿信"]})
    load_route_keywords({"line:Gtest": ["阿財"]})

    msg_config = _msg("阿信 你好")
    msg_db = _msg("阿財 你好")
    msg_none = _msg("阿明 你好")

    assert match_auto_trigger(msg_config, "mybot") is True
    assert match_auto_trigger(msg_db, "mybot") is True
    assert match_auto_trigger(msg_none, "mybot") is False


# ── Write-through cache ──────────────────────────────────────────


def test_add_route_keyword_immediate():
    """add_route_keyword updates cache immediately."""
    msg = _msg("阿財 你好")
    assert match_auto_trigger(msg, "mybot") is False

    add_route_keyword("line:Gtest", "阿財")
    assert match_auto_trigger(msg, "mybot") is True


def test_remove_route_keyword_immediate():
    """remove_route_keyword removes from cache immediately."""
    load_route_keywords({"line:Gtest": ["阿財"]})
    msg = _msg("阿財 你好")
    assert match_auto_trigger(msg, "mybot") is True

    remove_route_keyword("line:Gtest", "阿財")
    assert match_auto_trigger(msg, "mybot") is False


# ── get_route_keywords / get_config_keywords ─────────────────────


def test_get_route_keywords():
    load_route_keywords({"line:Gtest": ["阿財", "小財"]})
    assert get_route_keywords("line:Gtest") == ["阿財", "小財"]
    assert get_route_keywords("line:Gother") == []


def test_get_config_keywords():
    configure_auto_triggers({"mybot": ["阿信", "龍泰"]})
    kws = get_config_keywords("mybot")
    assert "阿信" in kws
    assert "龍泰" in kws
    assert get_config_keywords("otherbot") == []


# ── Private chat bypass ──────────────────────────────────────────


def test_private_chat_no_auto_trigger():
    """Auto-trigger doesn't fire in private chats."""
    configure_auto_triggers({"mybot": ["阿信"]})
    msg = Message(
        text="阿信 你好",
        user_id="Utest",
        user_name="Tester",
        platform="line",
        group_id=None,
        conversation_id="Utest",
        is_mention=False,
        timestamp=datetime(2026, 3, 28, 10, 0, tzinfo=timezone.utc),
    )
    assert match_auto_trigger(msg, "mybot") is False


# ── DB store integration ─────────────────────────────────────────


@pytest.fixture
async def store(tmp_path):
    s = SqliteMemoryStore(db_path=str(tmp_path / "test.db"))
    await s.initialize()
    yield s
    await s.close()


async def test_db_add_and_load(store):
    """DB add → load_all returns correct data."""
    await store.add_trigger_keyword("line:G1", "阿財")
    await store.add_trigger_keyword("line:G1", "小財")
    await store.add_trigger_keyword("line:G2", "老闆")

    all_kw = await store.load_all_trigger_keywords()
    assert set(all_kw["line:G1"]) == {"阿財", "小財"}
    assert all_kw["line:G2"] == ["老闆"]


async def test_db_remove(store):
    """DB remove → keyword gone."""
    await store.add_trigger_keyword("line:G1", "阿財")
    deleted = await store.remove_trigger_keyword("line:G1", "阿財")
    assert deleted is True

    kws = await store.list_trigger_keywords("line:G1")
    assert kws == []


async def test_db_remove_nonexistent(store):
    """Removing nonexistent keyword returns False."""
    deleted = await store.remove_trigger_keyword("line:G1", "不存在")
    assert deleted is False


async def test_db_duplicate_ignored(store):
    """Adding duplicate keyword is silently ignored (INSERT OR IGNORE)."""
    await store.add_trigger_keyword("line:G1", "阿財")
    await store.add_trigger_keyword("line:G1", "阿財")

    kws = await store.list_trigger_keywords("line:G1")
    assert kws == ["阿財"]


async def test_db_list(store):
    """list_trigger_keywords returns correct list."""
    await store.add_trigger_keyword("line:G1", "阿財")
    await store.add_trigger_keyword("line:G1", "小財")

    kws = await store.list_trigger_keywords("line:G1")
    assert kws == ["阿財", "小財"]

    kws_empty = await store.list_trigger_keywords("line:G999")
    assert kws_empty == []


# ── Full flow: DB write → cache update → trigger ─────────────────


async def test_full_write_through_flow(store):
    """DB write → cache update → match_auto_trigger works."""
    route_id = "line:Gfull"
    msg = _msg("阿財 你好", group_id="Gfull")

    # Before: no trigger
    assert match_auto_trigger(msg, "mybot") is False

    # Write to DB
    await store.add_trigger_keyword(route_id, "阿財")

    # Update cache (simulates what the tool handler does)
    add_route_keyword(route_id, "阿財")

    # After: triggers
    assert match_auto_trigger(msg, "mybot") is True

    # Remove
    await store.remove_trigger_keyword(route_id, "阿財")
    remove_route_keyword(route_id, "阿財")

    # After remove: no trigger
    assert match_auto_trigger(msg, "mybot") is False
