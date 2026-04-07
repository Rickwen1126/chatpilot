"""list_observation_candidates tool — shortlist query-relevant source routes."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable

from copilot.types import ToolInvocation, ToolResult

from chatpilot.core.types import AccessLevel, ObservationProfileConfig, ToolDefinition
from chatpilot.tools.session_context import get_session_context

logger = logging.getLogger(__name__)


def create_list_observation_candidates_tool(
    observation_groups: dict[str, dict],
    route_binding_service: Any,
    get_config: Callable[[], Any],
    load_route_labels: Callable[[], dict[str, str]],
) -> ToolDefinition:
    async def handler(invocation: ToolInvocation) -> ToolResult:
        args = invocation.get("arguments") or {}
        session_context = get_session_context(invocation)
        caller_route = session_context.route_id
        group_name = str(args.get("group", "")).strip()
        query = str(args.get("query", "")).strip()
        top_k = max(1, min(int(args.get("top_k", 3) or 3), 5))

        if not group_name:
            return ToolResult(
                textResultForLlm="需要指定 group。",
                resultType="failure",
            )

        state = observation_groups.get(group_name)
        if state is None:
            return ToolResult(
                textResultForLlm=f"找不到 group「{group_name}」",
                resultType="failure",
            )
        if caller_route not in state.get("consumer_route_ids", []):
            return ToolResult(
                textResultForLlm="無權限查詢此 group 的 observation candidates",
                resultType="failure",
            )

        config = get_config()
        labels = load_route_labels()
        candidates: list[dict[str, Any]] = []
        for route_id in state.get("source_route_ids", []):
            entry = route_binding_service.get_entry(route_id)
            observation = entry.observation if entry is not None else None
            capture = observation.capture if observation is not None else None
            profile_name = capture.profile if capture is not None else ""
            profile = config.observation_profiles.get(profile_name)
            label = labels.get(route_id, "")
            score, reasons = _score_candidate(query, label, profile)
            if score <= 0:
                continue
            candidates.append(
                {
                    "route_id": route_id,
                    "label": label,
                    "profile": profile_name,
                    "profile_description": _profile_description(profile),
                    "categories": list(profile.categories if profile else []),
                    "reason": "；".join(reasons),
                    "score": score,
                }
            )

        if not candidates:
            for route_id in state.get("source_route_ids", []):
                entry = route_binding_service.get_entry(route_id)
                observation = entry.observation if entry is not None else None
                capture = observation.capture if observation is not None else None
                profile_name = capture.profile if capture is not None else ""
                profile = config.observation_profiles.get(profile_name)
                label = labels.get(route_id, "")
                candidates.append(
                    {
                        "route_id": route_id,
                        "label": label,
                        "profile": profile_name,
                        "profile_description": _profile_description(profile),
                        "categories": list(profile.categories if profile else []),
                        "reason": (
                            "沒有明確語意命中；提供 group 內可查來源作為保底候選"
                        ),
                        "score": 0,
                    }
                )

        candidates.sort(
            key=lambda item: (-int(item["score"]), str(item["route_id"]))
        )
        shortlist = candidates[:top_k]
        for index, item in enumerate(shortlist, start=1):
            item["suggested_priority"] = index
        logger.info(
            "[obs_candidates] group=%s caller=%s query=%s shortlisted=%s",
            group_name,
            caller_route,
            query,
            [(item["route_id"], item["score"]) for item in shortlist],
        )

        return ToolResult(
            textResultForLlm=json.dumps(shortlist, ensure_ascii=False),
            resultType="success",
        )

    return ToolDefinition(
        name="list_observation_candidates",
        description=(
            "先根據 group 與自然語言 query，回傳最值得查的 observation "
            "source route shortlist。這個工具只給候選來源，不會直接給答案。"
            "先用這個工具，再至少選一個 member route 呼叫 query_observation_member。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "group": {"type": "string", "description": "observation group 名稱"},
                "query": {"type": "string", "description": "使用者的自然語言問題"},
                "top_k": {
                    "type": "integer",
                    "description": "最多回傳幾個 candidates（預設 3，最大 5）",
                },
            },
            "required": ["group", "query"],
        },
        handler=handler,
        access_level=AccessLevel.GLOBAL,
    )


def _score_candidate(
    query: str,
    label: str,
    profile: ObservationProfileConfig | None,
) -> tuple[int, list[str]]:
    normalized_query = query.casefold().strip()
    score = 0
    reasons: list[str] = []
    categories = [item for item in (profile.categories if profile else []) if item]
    keywords = _profile_keywords(profile)
    description = _profile_description(profile)

    if any(category.casefold() in normalized_query for category in categories):
        score += 4
        reasons.append("query 命中 profile categories")

    if any(keyword.casefold() in normalized_query for keyword in keywords):
        score += 3
        reasons.append("query 命中 retrieval keywords")

    if _has_phrase_overlap(normalized_query, description.casefold()):
        score += 2
        reasons.append("query 與 profile description 相關")

    normalized_label = label.casefold().strip()
    if normalized_label and _has_phrase_overlap(normalized_query, normalized_label):
        score += 1
        reasons.append("query 與 route label 相關")
    if normalized_label and normalized_label in normalized_query:
        score += 2
        reasons.append("query 命中完整 route label")

    return score, reasons


def _profile_description(profile: ObservationProfileConfig | None) -> str:
    if profile is None:
        return ""
    return profile.retrieval.description.strip() or profile.instructions.strip()


def _profile_keywords(profile: ObservationProfileConfig | None) -> list[str]:
    if profile is None:
        return []
    return [
        item
        for item in (profile.retrieval.keywords or profile.categories)
        if str(item).strip()
    ]


def _has_phrase_overlap(left: str, right: str) -> bool:
    if not left or not right:
        return False
    right_terms = _extract_phrases(right)
    return any(term in left for term in right_terms)


def _extract_phrases(text: str) -> list[str]:
    return re.findall(r"[a-z0-9_]{2,}|[\u4e00-\u9fff]{2,}", text.casefold())
