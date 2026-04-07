from __future__ import annotations

import json

import pytest

from chatpilot.core.config import GatewayConfig
from chatpilot.core.route_bindings import RouteBindingEntry
from chatpilot.tools.builtin.list_observation_candidates import (
    create_list_observation_candidates_tool,
)
from chatpilot.tools.builtin.query_observation_member import (
    create_query_observation_member_tool,
)


class _StubMemoryStore:
    async def query_observation_entries(
        self,
        route_id: str,
        query: str,
        *,
        days: int,
        limit: int,
        kinds: tuple[str, ...],
    ) -> list[dict]:
        return [
            {
                "id": "oe-1",
                "kind": "fact",
                "category": "請假",
                "subject": "阿明",
                "record_date": "2026-04-08",
                "content": "阿明明天下午請假",
                "reported_by_name": "小王",
                "source_observation_id": "obs-1",
            }
        ]

    async def get_observation_entries_by_ids(
        self, route_id: str, ids: list[str]
    ) -> list[dict]:
        return []


class _StubRouteBindingService:
    def __init__(self, entries: dict[str, RouteBindingEntry]) -> None:
        self._entries = entries

    def get_entry(self, route_id: str) -> RouteBindingEntry | None:
        return self._entries.get(route_id)


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
async def test_observation_retrieval_flow_shortlist_then_member_query() -> None:
    entries = {
        "line:demo:Cwarehouse": RouteBindingEntry(
            match={"platform": "line:demo", "group_id": "Cwarehouse"},
            chatbot="buddy",
            observation={"capture": {"group": "ops", "profile": "warehouse_ops"}},
            source="manual",
        )
    }
    observation_groups = {
        "ops": {
            "source_route_ids": ["line:demo:Cwarehouse"],
            "consumer_route_ids": ["line:demo:Uadmin"],
        }
    }
    config = GatewayConfig(
        observation_profiles={
            "warehouse_ops": {
                "mode": "batch",
                "batch_size": 10,
                "instructions": "capture",
                "categories": ["請假"],
                "retrieval": {
                    "description": "請假查詢",
                    "keywords": ["請假"],
                },
            }
        }
    )
    labels = {"line:demo:Cwarehouse": "倉庫群"}
    shortlist_tool = create_list_observation_candidates_tool(
        observation_groups,
        _StubRouteBindingService(entries),
        lambda: config,
        lambda: labels,
    )
    member_tool = create_query_observation_member_tool(
        _StubMemoryStore(),
        observation_groups,
        _StubRouteBindingService(entries),
        lambda: labels,
    )

    shortlist = await shortlist_tool.handler(
        {
            "session_context": _session_context("line:demo:Uadmin"),
            "arguments": {"group": "ops", "query": "最近誰請假？"},
        }
    )
    shortlist_payload = json.loads(shortlist["textResultForLlm"])
    route_id = shortlist_payload[0]["route_id"]

    result = await member_tool.handler(
        {
            "session_context": _session_context("line:demo:Uadmin"),
            "arguments": {"route_id": route_id, "query": "最近誰請假？"},
        }
    )
    payload = json.loads(result["textResultForLlm"])

    assert shortlist_payload[0]["route_id"] == "line:demo:Cwarehouse"
    assert payload["entries"][0]["subject"] == "阿明"
