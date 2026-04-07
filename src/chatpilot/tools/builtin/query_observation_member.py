"""query_observation_member tool — query projected observation rows for one route."""

from __future__ import annotations

import json
import logging
from typing import Any, Callable

from copilot.types import ToolInvocation, ToolResult

from chatpilot.core.types import AccessLevel, ToolDefinition
from chatpilot.tools.session_context import get_session_context

logger = logging.getLogger(__name__)


def create_query_observation_member_tool(
    memory_store: Any,
    observation_groups: dict[str, dict],
    route_binding_service: Any,
    load_route_labels: Callable[[], dict[str, str]],
) -> ToolDefinition:
    async def handler(invocation: ToolInvocation) -> ToolResult:
        args = invocation.get("arguments") or {}
        session_context = get_session_context(invocation)
        caller_route = session_context.route_id
        route_id = str(args.get("route_id", "")).strip()
        query = str(args.get("query", "")).strip()
        days = int(args.get("days", 30) or 30)
        limit = int(args.get("limit", 10) or 10)

        if not route_id:
            return ToolResult(
                textResultForLlm="需要指定 route_id。",
                resultType="failure",
            )

        allowed_routes = _allowed_source_routes(caller_route, observation_groups)
        if route_id not in allowed_routes:
            return ToolResult(
                textResultForLlm="無權限查詢這個 observation member route",
                resultType="failure",
            )

        rows = await memory_store.query_observation_entries(
            route_id,
            query,
            days=days,
            limit=max(limit * 3, limit),
            kinds=("fact", "semantic"),
        )
        fact_rows = await _resolve_fact_rows(memory_store, route_id, rows, limit=limit)
        logger.info(
            "[obs_member] caller=%s route=%s query=%s raw_hits=%d fact_hits=%d",
            caller_route,
            route_id,
            query,
            len(rows),
            len(fact_rows),
        )
        entry = route_binding_service.get_entry(route_id)
        observation = entry.observation if entry is not None else None
        capture = observation.capture if observation is not None else None
        labels = load_route_labels()
        payload = {
            "route_id": route_id,
            "label": labels.get(route_id, ""),
            "profile": capture.profile if capture is not None else "",
            "entries": [
                {
                    "id": row["id"],
                    "category": row["category"],
                    "subject": row["subject"],
                    "record_date": row["record_date"],
                    "content": row["content"],
                    "reported_by_name": row.get("reported_by_name"),
                    "evidence_ref": row["source_observation_id"],
                }
                for row in fact_rows
            ],
        }
        return ToolResult(
            textResultForLlm=json.dumps(payload, ensure_ascii=False),
            resultType="success",
        )

    return ToolDefinition(
        name="query_observation_member",
        description=(
            "針對單一 observation member route 查詢 route-owned observation "
            "projection。應先用 list_observation_candidates 取得候選，再決定查哪個 member。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "route_id": {"type": "string", "description": "要查的 source route_id"},
                "query": {"type": "string", "description": "自然語言問題"},
                "days": {"type": "integer", "description": "往回看幾天（預設 30）"},
                "limit": {"type": "integer", "description": "最多回傳幾筆（預設 10）"},
            },
            "required": ["route_id", "query"],
        },
        handler=handler,
        access_level=AccessLevel.GLOBAL,
    )


def _allowed_source_routes(
    caller_route: str, observation_groups: dict[str, dict]
) -> set[str]:
    allowed: set[str] = set()
    for group in observation_groups.values():
        if caller_route not in group.get("consumer_route_ids", []):
            continue
        allowed.update(group.get("source_route_ids", []))
    return allowed


async def _resolve_fact_rows(
    memory_store: Any,
    route_id: str,
    rows: list[dict[str, Any]],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    """Collapse fact+semantic hits into canonical fact rows."""
    if not rows:
        return []

    fact_by_id: dict[str, dict[str, Any]] = {
        str(row.get("id", "")): row for row in rows if row.get("kind") == "fact"
    }
    ordered_fact_ids: list[str] = []
    missing_fact_ids: list[str] = []
    seen: set[str] = set()

    for row in rows:
        row_id = str(row.get("id", "")).strip()
        row_kind = str(row.get("kind", "")).strip()
        if row_kind == "fact" and row_id:
            canonical_id = row_id
        elif row_kind == "semantic":
            canonical_id = str(row.get("canonical_entry_id", "")).strip()
        else:
            canonical_id = ""
        if not canonical_id or canonical_id in seen:
            continue
        seen.add(canonical_id)
        ordered_fact_ids.append(canonical_id)
        if canonical_id not in fact_by_id:
            missing_fact_ids.append(canonical_id)

    if missing_fact_ids and hasattr(memory_store, "get_observation_entries_by_ids"):
        fetched_rows = await memory_store.get_observation_entries_by_ids(
            route_id, missing_fact_ids
        )
        for row in fetched_rows:
            if row.get("kind") == "fact":
                fact_by_id[str(row.get("id", ""))] = row

    return [
        fact_by_id[fact_id]
        for fact_id in ordered_fact_ids
        if fact_id in fact_by_id
    ][:limit]
