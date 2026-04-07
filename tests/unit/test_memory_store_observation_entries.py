from chatpilot.memory.store import SqliteMemoryStore
from chatpilot.memory.types import ObservationEntry


async def test_save_and_list_observation_entries(tmp_path) -> None:
    store = SqliteMemoryStore(db_path=str(tmp_path / "entries.db"))
    await store.initialize()
    try:
        entry = ObservationEntry(
            route_id="line:demo:Cops",
            captured_profile_name="warehouse_ops",
            kind="fact",
            category="請假",
            subject="阿明",
            record_date="2026-04-07",
            content="阿明明天下午請假",
            search_text="阿明 請假 休假",
            reported_by_user_id="U1",
            reported_by_name="小王",
            facets_json={"aliases": ["休假"]},
            source_observation_id="obs-1",
        )
        ids = await store.save_observation_entries([entry])
        rows = await store.list_observation_entries("line:demo:Cops")
    finally:
        await store.close()

    assert ids == [entry.id]
    assert len(rows) == 1
    assert rows[0]["subject"] == "阿明"
    assert rows[0]["facets_json"]["aliases"] == ["休假"]


async def test_query_observation_entries_filters_by_route_and_terms(tmp_path) -> None:
    store = SqliteMemoryStore(db_path=str(tmp_path / "entries-query.db"))
    await store.initialize()
    try:
        await store.save_observation_entries(
            [
                ObservationEntry(
                    route_id="line:demo:Cops",
                    captured_profile_name="warehouse_ops",
                    kind="fact",
                    category="請假",
                    subject="阿明",
                    record_date="2099-04-07",
                    content="阿明明天下午請假",
                    search_text="阿明 請假 休假 半天",
                    reported_by_name="小王",
                    source_observation_id="obs-1",
                ),
                ObservationEntry(
                    route_id="line:demo:Cops",
                    captured_profile_name="warehouse_ops",
                    kind="fact",
                    category="進料",
                    subject="白漆",
                    record_date="2099-04-07",
                    content="白漆今天進料 20 桶",
                    search_text="白漆 進料 補貨 20桶",
                    reported_by_name="小王",
                    source_observation_id="obs-1",
                ),
                ObservationEntry(
                    route_id="line:demo:Cother",
                    captured_profile_name="warehouse_ops",
                    kind="fact",
                    category="請假",
                    subject="阿美",
                    record_date="2099-04-07",
                    content="阿美請假",
                    search_text="阿美 請假",
                    reported_by_name="小張",
                    source_observation_id="obs-2",
                ),
            ]
        )
        rows = await store.query_observation_entries(
            "line:demo:Cops",
            "阿明 請假",
            days=30,
            limit=10,
        )
    finally:
        await store.close()

    assert len(rows) == 1
    assert rows[0]["route_id"] == "line:demo:Cops"
    assert rows[0]["subject"] == "阿明"


async def test_query_observation_entries_supports_fuzzy_chinese_terms(tmp_path) -> None:
    store = SqliteMemoryStore(db_path=str(tmp_path / "entries-fuzzy.db"))
    await store.initialize()
    try:
        await store.save_observation_entries(
            [
                ObservationEntry(
                    route_id="line:demo:Cops",
                    captured_profile_name="warehouse_ops",
                    kind="fact",
                    category="請假",
                    subject="阿明",
                    record_date="2099-04-07",
                    content="阿明明天下午請假",
                    search_text="阿明 請假 休假 半天",
                    reported_by_name="小王",
                    source_observation_id="obs-1",
                )
            ]
        )
        rows = await store.query_observation_entries(
            "line:demo:Cops",
            "請假紀錄",
            days=30,
            limit=10,
        )
    finally:
        await store.close()

    assert len(rows) == 1
    assert rows[0]["category"] == "請假"
