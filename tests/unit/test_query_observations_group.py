from __future__ import annotations

import pytest

from chatpilot.tools.builtin.query_observations import (
    create_query_observations_tool,
)


class _StubMemoryStore:
    def __init__(self) -> None:
        self.queries: list[tuple[str, int, str]] = []

    async def query_observations(
        self, route_id: str, *, days: int, category: str
    ) -> list[dict]:
        self.queries.append((route_id, days, category))
        return [{
            "entries": [{
                "who": "阿明",
                "category": category or "請假",
                "content": f"{route_id} content",
                "timestamp": "2026-04-06T10:00:00Z",
            }]
        }]


def _session_context(route_id: str) -> dict[str, str]:
    platform, conversation_id = route_id.rsplit(":", 1)
    return {
        "sdk_session_id": f"{route_id.replace(':', '-')}__tester",
        "route_id": route_id,
        "platform": platform,
        "conversation_id": conversation_id,
        "chatbot_name": "tester",
    }


@pytest.mark.asyncio
async def test_query_observations_group_expands_multiple_source_routes() -> None:
    store = _StubMemoryStore()
    tool = create_query_observations_tool(
        store,
        {
            "ops": {
                "source_route_ids": [
                    "line:shinyipaint:C123",
                    "line:shinyipaint:C456",
                ],
                "consumer_route_ids": ["line:shinyipaint:Uadmin"],
            }
        },
    )

    result = await tool.handler({
        "session_context": _session_context("line:shinyipaint:Uadmin"),
        "arguments": {
            "group": "ops",
            "category": "請假",
            "days": 30,
        },
    })

    assert result["resultType"] == "success"
    assert store.queries == [
        ("line:shinyipaint:C123", 30, "請假"),
        ("line:shinyipaint:C456", 30, "請假"),
    ]
    assert "group=ops" in result["textResultForLlm"]


@pytest.mark.asyncio
async def test_query_observations_group_rejects_non_consumer_route() -> None:
    store = _StubMemoryStore()
    tool = create_query_observations_tool(
        store,
        {
            "ops": {
                "source_route_ids": ["line:shinyipaint:C123"],
                "consumer_route_ids": ["line:shinyipaint:Uadmin"],
            }
        },
    )

    result = await tool.handler({
        "session_context": _session_context("line:shinyipaint:Uguest"),
        "arguments": {"group": "ops"},
    })

    assert result["resultType"] == "failure"
    assert "無權限" in result["textResultForLlm"]
    assert store.queries == []
