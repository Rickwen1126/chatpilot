from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, Field

from chatpilot.core.types import ContextMessage
from chatpilot.memory.types import ObservationEntry


class ObservationWorkerFact(BaseModel):
    category: str = "其他"
    subject: str = ""
    record_date: str = ""
    content: str = ""
    reported_by_name: str | None = None
    search_text: str = ""
    facets_json: dict[str, Any] = Field(default_factory=dict)


class ObservationWorkerSemantic(BaseModel):
    canonical_fact_index: int | None = None
    category: str = "其他"
    subject: str = ""
    record_date: str = ""
    content: str = ""
    reported_by_name: str | None = None
    search_text: str = ""
    facets_json: dict[str, Any] = Field(default_factory=dict)


class ObservationWorkerResult(BaseModel):
    summary: str = ""
    facts: list[ObservationWorkerFact] = Field(default_factory=list)
    semantic: list[ObservationWorkerSemantic] = Field(default_factory=list)


def parse_observation_worker_result(raw: str) -> ObservationWorkerResult:
    """Parse worker JSON output, tolerating fenced or legacy array output."""
    data = _extract_json_payload(raw)
    if isinstance(data, list):
        facts = [
            ObservationWorkerFact(
                category=str(item.get("category", "其他") or "其他"),
                subject=str(
                    item.get("subject")
                    or item.get("who")
                    or item.get("target")
                    or ""
                ),
                record_date=_normalize_record_date(
                    item.get("record_date") or item.get("timestamp") or ""
                ),
                content=str(item.get("content", "")),
                reported_by_name=_clean_str(item.get("reported_by_name")),
                search_text=str(item.get("search_text", "")),
                facets_json=_coerce_dict(item.get("facets_json")),
            )
            for item in data
            if isinstance(item, dict) and str(item.get("content", "")).strip()
        ]
        return ObservationWorkerResult(summary="", facts=facts, semantic=[])

    if not isinstance(data, dict):
        raise ValueError("worker output is not a JSON object")

    facts = [
        ObservationWorkerFact.model_validate(item)
        for item in data.get("facts", [])
        if isinstance(item, dict)
    ]
    semantic = [
        ObservationWorkerSemantic.model_validate(item)
        for item in data.get("semantic", [])
        if isinstance(item, dict)
    ]
    return ObservationWorkerResult(
        summary=str(data.get("summary", "")),
        facts=facts,
        semantic=semantic,
    )


def build_memory_observation_entries(
    result: ObservationWorkerResult,
) -> list[dict[str, Any]]:
    """Build compatibility-friendly batch entries for memory_observations."""
    entries: list[dict[str, Any]] = []
    for fact in result.facts:
        entries.append(
            {
                "category": fact.category or "其他",
                "subject": fact.subject,
                "who": fact.subject,
                "record_date": _normalize_record_date(fact.record_date),
                "timestamp": _normalize_record_date(fact.record_date),
                "content": fact.content,
                "reported_by_name": fact.reported_by_name or "",
                "search_text": fact.search_text or "",
                "facets_json": fact.facets_json,
            }
        )
    return entries


def project_observation_entries(
    *,
    route_id: str,
    source_observation_id: str,
    captured_profile_name: str,
    messages: list[ContextMessage],
    result: ObservationWorkerResult,
) -> list[ObservationEntry]:
    """Project worker result into route-owned retrieval rows."""
    entries: list[ObservationEntry] = []
    reporter_ids = _build_reporter_lookup(messages)
    fact_ids: list[str] = []

    for fact in result.facts:
        reporter_name = _clean_str(fact.reported_by_name)
        entry = ObservationEntry(
            route_id=route_id,
            captured_profile_name=captured_profile_name,
            kind="fact",
            category=fact.category or "其他",
            subject=fact.subject,
            record_date=_normalize_record_date(fact.record_date),
            content=fact.content,
            search_text=_build_search_text(
                fact.search_text,
                fact.category,
                fact.subject,
                fact.content,
                reporter_name,
                fact.facets_json,
            ),
            reported_by_user_id=reporter_ids.get(reporter_name or ""),
            reported_by_name=reporter_name,
            facets_json=_coerce_dict(fact.facets_json),
            source_observation_id=source_observation_id,
        )
        fact_ids.append(entry.id)
        entries.append(entry)

    for semantic in result.semantic:
        canonical_id = None
        idx = semantic.canonical_fact_index
        if idx is not None and 0 <= idx < len(fact_ids):
            canonical_id = fact_ids[idx]
        reporter_name = _clean_str(semantic.reported_by_name)
        entries.append(
            ObservationEntry(
                route_id=route_id,
                captured_profile_name=captured_profile_name,
                kind="semantic",
                canonical_entry_id=canonical_id,
                category=semantic.category or "其他",
                subject=semantic.subject,
                record_date=_normalize_record_date(semantic.record_date),
                content=semantic.content,
                search_text=_build_search_text(
                    semantic.search_text,
                    semantic.category,
                    semantic.subject,
                    semantic.content,
                    reporter_name,
                    semantic.facets_json,
                ),
                reported_by_user_id=reporter_ids.get(reporter_name or ""),
                reported_by_name=reporter_name,
                facets_json=_coerce_dict(semantic.facets_json),
                source_observation_id=source_observation_id,
            )
        )

    return entries


def _extract_json_payload(raw: str) -> Any:
    text = raw.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"(\{.*\}|\[.*\])", text, re.DOTALL)
        if not match:
            raise ValueError("worker output does not contain JSON payload") from None
        return json.loads(match.group(1))


def _normalize_record_date(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) >= 10 and text[4:5] == "-" and text[7:8] == "-":
        return text[:10]
    return text


def _coerce_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _clean_str(value: Any) -> str | None:
    text = str(value).strip() if value not in (None, "") else ""
    return text or None


def _build_reporter_lookup(messages: list[ContextMessage]) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for message in messages:
        lookup.setdefault(message.user_name, message.user_id)
    return lookup


def _build_search_text(
    explicit: str,
    category: str,
    subject: str,
    content: str,
    reporter_name: str | None,
    facets_json: dict[str, Any],
) -> str:
    parts: list[str] = []
    for item in [explicit, category, subject, content, reporter_name or ""]:
        text = str(item or "").strip()
        if text:
            parts.append(text)
    for value in facets_json.values():
        if isinstance(value, str) and value.strip():
            parts.append(value.strip())
        elif isinstance(value, list):
            parts.extend(
                item.strip()
                for item in value
                if isinstance(item, str) and item.strip()
            )
    deduped: list[str] = []
    seen: set[str] = set()
    for item in parts:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return " ".join(deduped)
