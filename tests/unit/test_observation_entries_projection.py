from datetime import datetime, timezone

from chatpilot.core.types import ContextMessage, ContextMessageType
from chatpilot.observer.projection import (
    ObservationWorkerResult,
    build_memory_observation_entries,
    parse_observation_worker_result,
    project_observation_entries,
)


def test_parse_observation_worker_result_object_shape() -> None:
    raw = """
{
  "summary": "1 筆請假",
  "facts": [
    {
      "category": "請假",
      "subject": "阿明",
      "record_date": "2026-04-08",
      "content": "阿明明天下午請假",
      "reported_by_name": "小王",
      "search_text": "阿明 請假 休假",
      "facets_json": {"aliases": ["休假"]}
    }
  ],
  "semantic": [
    {
      "canonical_fact_index": 0,
      "category": "請假",
      "subject": "阿明",
      "record_date": "2026-04-08",
      "content": "阿明明天下午不在",
      "reported_by_name": "小王",
      "search_text": "阿明 不在 休假",
      "facets_json": {"intent_aliases": ["不在"]}
    }
  ]
}
"""

    result = parse_observation_worker_result(raw)

    assert result.summary == "1 筆請假"
    assert len(result.facts) == 1
    assert len(result.semantic) == 1
    assert result.semantic[0].canonical_fact_index == 0


def test_projection_builds_fact_and_semantic_rows() -> None:
    result = ObservationWorkerResult.model_validate(
        {
            "summary": "1 筆請假",
            "facts": [
                {
                    "category": "請假",
                    "subject": "阿明",
                    "record_date": "2026-04-08",
                    "content": "阿明明天下午請假",
                    "reported_by_name": "小王",
                    "search_text": "阿明 請假",
                    "facets_json": {"aliases": ["休假"]},
                }
            ],
            "semantic": [
                {
                    "canonical_fact_index": 0,
                    "category": "請假",
                    "subject": "阿明",
                    "record_date": "2026-04-08",
                    "content": "阿明明天下午不在",
                    "reported_by_name": "小王",
                    "search_text": "阿明 不在 休假",
                    "facets_json": {"intent_aliases": ["不在"]},
                }
            ],
        }
    )
    messages = [
        ContextMessage(
            user_id="U1",
            user_name="小王",
            text="阿明明天下午請假",
            timestamp=datetime(2026, 4, 7, 9, 0, tzinfo=timezone.utc),
            message_type=ContextMessageType.background,
        )
    ]

    entries = project_observation_entries(
        route_id="line:demo:Cops",
        source_observation_id="obs-1",
        captured_profile_name="warehouse_ops",
        messages=messages,
        result=result,
    )
    memory_entries = build_memory_observation_entries(result)

    assert len(entries) == 2
    assert entries[0].kind == "fact"
    assert entries[0].reported_by_user_id == "U1"
    assert entries[1].kind == "semantic"
    assert entries[1].canonical_entry_id == entries[0].id
    assert memory_entries[0]["who"] == "阿明"
    assert memory_entries[0]["timestamp"] == "2026-04-08"
