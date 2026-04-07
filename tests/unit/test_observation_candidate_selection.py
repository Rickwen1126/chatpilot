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
async def test_list_observation_candidates_uses_query_time_group_membership() -> None:
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
                            "profile": "warehouse_ops",
                        }
                    },
                    source="manual",
                )
            }
        ),
        lambda: GatewayConfig(
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
        ),
        lambda: {"line:demo:Cwarehouse": "倉庫群"},
    )

    result = await tool.handler(
        {
            "session_context": _session_context("line:demo:Uadmin"),
            "arguments": {"group": "ops", "query": "請假"},
        }
    )

    payload = json.loads(result["textResultForLlm"])
    assert len(payload) == 1
    assert payload[0]["route_id"] == "line:demo:Cwarehouse"
