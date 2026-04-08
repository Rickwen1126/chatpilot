from __future__ import annotations

import json

import pytest

from chatpilot.core.route_bindings import RouteBindingEntry
from chatpilot.tools.builtin.query_observation_member import (
    create_query_observation_member_tool,
)


class _StubMemoryStore:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, int, int, tuple[str, ...]]] = []
        self.get_calls: list[tuple[str, tuple[str, ...]]] = []

    async def query_observation_entries(
        self,
        route_id: str,
        query: str,
        *,
        days: int,
        limit: int,
        kinds: tuple[str, ...],
    ) -> list[dict]:
        self.calls.append((route_id, query, days, limit, kinds))
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
        self.get_calls.append((route_id, tuple(ids)))
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
async def test_query_observation_member_returns_per_source_results() -> None:
    store = _StubMemoryStore()
    tool = create_query_observation_member_tool(
        store,
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
        lambda: {"line:demo:Cwarehouse": "倉庫群"},
    )

    result = await tool.handler(
        {
            "session_context": _session_context("line:demo:Uadmin"),
            "arguments": {
                "route_id": "line:demo:Cwarehouse",
                "query": "最近誰請假？",
                "days": 30,
                "limit": 10,
            },
        }
    )

    assert result["resultType"] == "success"
    payload = json.loads(result["textResultForLlm"])
    assert payload["route_id"] == "line:demo:Cwarehouse"
    assert payload["profile"] == "warehouse_ops"
    assert payload["entries"][0]["subject"] == "阿明"
    assert store.calls == [
        ("line:demo:Cwarehouse", "最近誰請假？", 30, 30, ("fact", "semantic"))
    ]
    assert store.get_calls == []


class _SemanticHitStore(_StubMemoryStore):
    async def query_observation_entries(
        self,
        route_id: str,
        query: str,
        *,
        days: int,
        limit: int,
        kinds: tuple[str, ...],
    ) -> list[dict]:
        self.calls.append((route_id, query, days, limit, kinds))
        return [
            {
                "id": "oe-sem-1",
                "kind": "semantic",
                "canonical_entry_id": "oe-fact-1",
                "category": "請假",
                "subject": "阿明",
                "record_date": "2026-04-08",
                "content": "阿明明天下午不在",
                "reported_by_name": "小王",
                "source_observation_id": "obs-1",
            }
        ]

    async def get_observation_entries_by_ids(
        self, route_id: str, ids: list[str]
    ) -> list[dict]:
        self.get_calls.append((route_id, tuple(ids)))
        return [
            {
                "id": "oe-fact-1",
                "kind": "fact",
                "category": "請假",
                "subject": "阿明",
                "record_date": "2026-04-08",
                "content": "阿明明天下午請假",
                "reported_by_name": "小王",
                "source_observation_id": "obs-1",
            }
        ]


@pytest.mark.asyncio
async def test_query_observation_member_resolves_semantic_hits_back_to_fact() -> None:
    store = _SemanticHitStore()
    tool = create_query_observation_member_tool(
        store,
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
        lambda: {"line:demo:Cwarehouse": "倉庫群"},
    )

    result = await tool.handler(
        {
            "session_context": _session_context("line:demo:Uadmin"),
            "arguments": {
                "route_id": "line:demo:Cwarehouse",
                "query": "明天下午誰不在？",
                "days": 30,
                "limit": 10,
            },
        }
    )

    assert result["resultType"] == "success"
    payload = json.loads(result["textResultForLlm"])
    assert payload["entries"] == [
        {
            "id": "oe-fact-1",
            "category": "請假",
            "subject": "阿明",
            "record_date": "2026-04-08",
            "content": "阿明明天下午請假",
            "reported_by_name": "小王",
            "evidence_ref": "obs-1",
        }
    ]
    assert store.calls == [
        ("line:demo:Cwarehouse", "明天下午誰不在？", 30, 30, ("fact", "semantic"))
    ]
    assert store.get_calls == [("line:demo:Cwarehouse", ("oe-fact-1",))]


class _MixedHitStore(_StubMemoryStore):
    async def query_observation_entries(
        self,
        route_id: str,
        query: str,
        *,
        days: int,
        limit: int,
        kinds: tuple[str, ...],
    ) -> list[dict]:
        self.calls.append((route_id, query, days, limit, kinds))
        return [
            {
                "id": "oe-sem-1",
                "kind": "semantic",
                "canonical_entry_id": "oe-fact-1",
                "category": "請假",
                "subject": "阿明",
                "record_date": "2026-04-08",
                "content": "阿明明天下午不在",
                "reported_by_name": "小王",
                "source_observation_id": "obs-1",
            },
            {
                "id": "oe-fact-1",
                "kind": "fact",
                "category": "請假",
                "subject": "阿明",
                "record_date": "2026-04-08",
                "content": "阿明明天下午請假",
                "reported_by_name": "小王",
                "source_observation_id": "obs-1",
            },
        ]


@pytest.mark.asyncio
async def test_query_observation_member_dedupes_fact_and_semantic_hits() -> None:
    store = _MixedHitStore()
    tool = create_query_observation_member_tool(
        store,
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
        lambda: {"line:demo:Cwarehouse": "倉庫群"},
    )

    result = await tool.handler(
        {
            "session_context": _session_context("line:demo:Uadmin"),
            "arguments": {
                "route_id": "line:demo:Cwarehouse",
                "query": "明天下午誰不在？",
                "days": 30,
                "limit": 10,
            },
        }
    )

    payload = json.loads(result["textResultForLlm"])
    assert [entry["id"] for entry in payload["entries"]] == ["oe-fact-1"]
    assert store.get_calls == []


class _MultiAliasSemanticStore(_StubMemoryStore):
    async def query_observation_entries(
        self,
        route_id: str,
        query: str,
        *,
        days: int,
        limit: int,
        kinds: tuple[str, ...],
    ) -> list[dict]:
        self.calls.append((route_id, query, days, limit, kinds))
        return [
            {
                "id": "oe-sem-1",
                "kind": "semantic",
                "canonical_entry_id": "oe-fact-1",
                "category": "請假",
                "subject": "阿明",
                "record_date": "2026-04-08",
                "content": "阿明明天下午不在",
                "reported_by_name": "小王",
                "source_observation_id": "obs-1",
            },
            {
                "id": "oe-sem-2",
                "kind": "semantic",
                "canonical_entry_id": "oe-fact-1",
                "category": "請假",
                "subject": "阿明",
                "record_date": "2026-04-08",
                "content": "阿明明天下午缺席",
                "reported_by_name": "小王",
                "source_observation_id": "obs-1",
            },
            {
                "id": "oe-sem-3",
                "kind": "semantic",
                "canonical_entry_id": "oe-fact-2",
                "category": "請假",
                "subject": "阿美",
                "record_date": "2026-04-09",
                "content": "阿美明天不在",
                "reported_by_name": "小張",
                "source_observation_id": "obs-2",
            },
        ]

    async def get_observation_entries_by_ids(
        self, route_id: str, ids: list[str]
    ) -> list[dict]:
        self.get_calls.append((route_id, tuple(ids)))
        return [
            {
                "id": "oe-fact-1",
                "kind": "fact",
                "category": "請假",
                "subject": "阿明",
                "record_date": "2026-04-08",
                "content": "阿明明天下午請假",
                "reported_by_name": "小王",
                "source_observation_id": "obs-1",
            },
            {
                "id": "oe-fact-2",
                "kind": "fact",
                "category": "請假",
                "subject": "阿美",
                "record_date": "2026-04-09",
                "content": "阿美明天請假",
                "reported_by_name": "小張",
                "source_observation_id": "obs-2",
            },
        ]


@pytest.mark.asyncio
async def test_query_observation_member_dedupes_multiple_semantic_aliases_and_respects_limit(  # noqa: E501
) -> None:
    store = _MultiAliasSemanticStore()
    tool = create_query_observation_member_tool(
        store,
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
        lambda: {"line:demo:Cwarehouse": "倉庫群"},
    )

    result = await tool.handler(
        {
            "session_context": _session_context("line:demo:Uadmin"),
            "arguments": {
                "route_id": "line:demo:Cwarehouse",
                "query": "明天誰不在？",
                "days": 30,
                "limit": 1,
            },
        }
    )

    payload = json.loads(result["textResultForLlm"])
    assert [entry["id"] for entry in payload["entries"]] == ["oe-fact-1"]
    assert store.get_calls == [("line:demo:Cwarehouse", ("oe-fact-1", "oe-fact-2"))]


class _BrokenSemanticStore(_StubMemoryStore):
    async def query_observation_entries(
        self,
        route_id: str,
        query: str,
        *,
        days: int,
        limit: int,
        kinds: tuple[str, ...],
    ) -> list[dict]:
        self.calls.append((route_id, query, days, limit, kinds))
        return [
            {
                "id": "oe-sem-1",
                "kind": "semantic",
                "canonical_entry_id": "",
                "category": "請假",
                "subject": "阿明",
                "record_date": "2026-04-08",
                "content": "阿明明天下午不在",
                "reported_by_name": "小王",
                "source_observation_id": "obs-1",
            }
        ]


@pytest.mark.asyncio
async def test_query_observation_member_ignores_broken_semantic_rows_without_canonical_fact(  # noqa: E501
) -> None:
    store = _BrokenSemanticStore()
    tool = create_query_observation_member_tool(
        store,
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
        lambda: {"line:demo:Cwarehouse": "倉庫群"},
    )

    result = await tool.handler(
        {
            "session_context": _session_context("line:demo:Uadmin"),
            "arguments": {
                "route_id": "line:demo:Cwarehouse",
                "query": "明天下午誰不在？",
                "days": 30,
                "limit": 10,
            },
        }
    )

    payload = json.loads(result["textResultForLlm"])
    assert payload["entries"] == []
    assert store.get_calls == []


@pytest.mark.asyncio
async def test_query_observation_member_rejects_unauthorized_route() -> None:
    store = _StubMemoryStore()
    tool = create_query_observation_member_tool(
        store,
        {
            "ops": {
                "source_route_ids": ["line:demo:Cwarehouse"],
                "consumer_route_ids": ["line:demo:Uadmin"],
            }
        },
        _StubRouteBindingService({}),
        lambda: {},
    )

    result = await tool.handler(
        {
            "session_context": _session_context("line:demo:Uguest"),
            "arguments": {
                "route_id": "line:demo:Cwarehouse",
                "query": "最近誰請假？",
            },
        }
    )

    assert result["resultType"] == "failure"
    assert "無權限" in result["textResultForLlm"]
    assert store.calls == []
