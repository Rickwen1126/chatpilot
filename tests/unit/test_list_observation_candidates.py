from __future__ import annotations

import json

import pytest

from chatpilot.core.config import GatewayConfig
from chatpilot.core.route_bindings import RouteBindingEntry
from chatpilot.tools.builtin.list_observation_candidates import (
    create_list_observation_candidates_tool,
)


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
async def test_list_observation_candidates_scores_top_k() -> None:
    config = GatewayConfig(
        observation_profiles={
            "warehouse_ops": {
                "mode": "batch",
                "batch_size": 10,
                "instructions": "營運倉庫整理",
                "categories": ["請假", "進料", "庫存"],
                "retrieval": {
                    "description": "適合請假、進出料與庫存查詢",
                    "keywords": ["請假", "庫存", "進料"],
                },
            },
            "marketing_ops": {
                "mode": "batch",
                "batch_size": 10,
                "instructions": "行銷活動整理",
                "categories": ["活動", "客訴"],
                "retrieval": {
                    "description": "適合活動與客訴查詢",
                    "keywords": ["活動", "客訴"],
                },
            },
        }
    )
    tool = create_list_observation_candidates_tool(
        {
            "ops": {
                "source_route_ids": [
                    "line:demo:Cwarehouse",
                    "line:demo:Cmarketing",
                ],
                "consumer_route_ids": ["line:demo:Uadmin"],
            }
        },
        _StubRouteBindingService(
            {
                "line:demo:Cwarehouse": RouteBindingEntry(
                    match={"platform": "line:demo", "group_id": "Cwarehouse"},
                    chatbot="buddy",
                    observation={
                        "capture": {
                            "group": "ops",
                            "profile": "warehouse_ops",
                        }
                    },
                    source="manual",
                ),
                "line:demo:Cmarketing": RouteBindingEntry(
                    match={"platform": "line:demo", "group_id": "Cmarketing"},
                    chatbot="buddy",
                    observation={
                        "capture": {
                            "group": "ops",
                            "profile": "marketing_ops",
                        }
                    },
                    source="manual",
                ),
            }
        ),
        lambda: config,
        lambda: {
            "line:demo:Cwarehouse": "倉庫群",
            "line:demo:Cmarketing": "行銷群",
        },
    )

    result = await tool.handler(
        {
            "session_context": _session_context("line:demo:Uadmin"),
            "arguments": {
                "group": "ops",
                "query": "最近誰請假？",
                "top_k": 3,
            },
        }
    )

    assert result["resultType"] == "success"
    payload = json.loads(result["textResultForLlm"])
    assert payload[0]["route_id"] == "line:demo:Cwarehouse"
    assert payload[0]["score"] > 0
    assert payload[0]["suggested_priority"] == 1


@pytest.mark.asyncio
async def test_list_observation_candidates_rejects_non_consumer() -> None:
    tool = create_list_observation_candidates_tool(
        {
            "ops": {
                "source_route_ids": ["line:demo:Cwarehouse"],
                "consumer_route_ids": ["line:demo:Uadmin"],
            }
        },
        _StubRouteBindingService({}),
        lambda: GatewayConfig(),
        lambda: {},
    )

    result = await tool.handler(
        {
            "session_context": _session_context("line:demo:Uguest"),
            "arguments": {"group": "ops", "query": "請假"},
        }
    )

    assert result["resultType"] == "failure"
    assert "無權限" in result["textResultForLlm"]


@pytest.mark.asyncio
async def test_list_observation_candidates_returns_fallback_when_scores_are_zero() -> None:
    config = GatewayConfig(
        observation_profiles={
            "ops_batch": {
                "mode": "batch",
                "batch_size": 10,
                "instructions": "capture",
                "categories": ["leave", "inventory"],
                "retrieval": {
                    "description": "English-only operational profile",
                    "keywords": ["leave", "inventory"],
                },
            }
        }
    )
    tool = create_list_observation_candidates_tool(
        {
            "ops": {
                "source_route_ids": ["line:demo:Cwarehouse"],
                "consumer_route_ids": ["line:demo:Uadmin"],
            }
        },
        _StubRouteBindingService(
            {
                "line:demo:Cwarehouse": RouteBindingEntry(
                    match={"platform": "line:demo", "group_id": "Cwarehouse"},
                    chatbot="buddy",
                    observation={
                        "capture": {
                            "group": "ops",
                            "profile": "ops_batch",
                        }
                    },
                    source="manual",
                )
            }
        ),
        lambda: config,
        lambda: {"line:demo:Cwarehouse": "倉庫群"},
    )

    result = await tool.handler(
        {
            "session_context": _session_context("line:demo:Uadmin"),
            "arguments": {"group": "ops", "query": "請假紀錄"},
        }
    )

    assert result["resultType"] == "success"
    payload = json.loads(result["textResultForLlm"])
    assert payload[0]["route_id"] == "line:demo:Cwarehouse"
    assert payload[0]["score"] == 0
    assert "保底候選" in payload[0]["reason"]
