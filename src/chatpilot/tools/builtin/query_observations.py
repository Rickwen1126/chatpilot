"""query_observations tool — query observer data across chats."""

from __future__ import annotations

import logging
from typing import Any

from copilot.types import ToolInvocation, ToolResult

from chatpilot.core.types import AccessLevel, ToolDefinition
from chatpilot.tools.session_context import get_session_context

logger = logging.getLogger(__name__)


def create_query_observations_tool(
    memory_store: Any,
    observation_groups: dict[str, dict] | None = None,
) -> ToolDefinition:
    """Create query_observations tool.

    observation_groups: {
        "main_group": {
            "source_route_ids": ["line:shinyipaint:Csource"],
            "consumer_route_ids": ["line:shinyipaint:Ufc68"]
        }
    }
    """
    sources = observation_groups or {}

    async def handler(invocation: ToolInvocation) -> ToolResult:
        args = invocation.get("arguments") or {}
        session_context = get_session_context(invocation)
        caller_route = session_context.route_id

        group_name = args.get("group", "")
        category = args.get("category", "")
        days = args.get("days", 7)

        if not group_name:
            available = list(sources.keys())
            return ToolResult(
                textResultForLlm=(
                    f"需要指定 group。可用：{', '.join(available)}"
                    if available
                    else "沒有設定可查詢的 observation group"
                ),
                resultType="failure",
            )

        group = sources.get(group_name)
        if group is None:
            return ToolResult(
                textResultForLlm=f"找不到 group「{group_name}」",
                resultType="failure",
            )

        allowed = group.get("consumer_route_ids", [])
        if caller_route not in allowed:
            logger.info(
                "[query_obs] denied: caller=%s not in %s",
                caller_route, allowed,
            )
            return ToolResult(
                textResultForLlm="無權限查詢此 group 的觀察資料",
                resultType="failure",
            )

        all_routes = group.get("source_route_ids", [])
        logger.info(
            "[query_obs] group=%s caller=%s routes=%s cat=%s days=%s",
            group_name, caller_route, all_routes, category, days,
        )
        try:
            observations = []
            for sr in all_routes:
                obs = await memory_store.query_observations(
                    sr, days=days, category=category
                )
                logger.info("[query_obs] %s → %d batches", sr, len(obs))
                observations.extend(obs)
        except Exception as e:
            return ToolResult(
                textResultForLlm=f"查詢失敗: {e}",
                resultType="failure",
            )

        if not observations:
            msg = f"過去 {days} 天沒有觀察紀錄"
            if category:
                msg += f"（分類：{category}）"
            return ToolResult(
                textResultForLlm=msg, resultType="success"
            )

        # Format results
        lines = []
        total_entries = 0
        for obs in observations:
            for entry in obs.get("entries", []):
                who = entry.get("subject") or entry.get("who", "?")
                cat = entry.get("category", "")
                content = entry.get("content", "")
                ts = entry.get("record_date") or entry.get("timestamp", "")
                reported_by = entry.get("reported_by_name", "")
                suffix = f" ({ts})" if ts else ""
                if reported_by and reported_by != who:
                    suffix = (
                        f"（提供者: {reported_by}，{ts}）"
                        if ts
                        else f"（提供者: {reported_by}）"
                    )
                lines.append(f"• [{cat}] {who}: {content}{suffix}")
                total_entries += 1

        header = f"觀察紀錄（group={group_name}，{total_entries} 筆"
        if category:
            header += f"，分類：{category}"
        header += f"，過去 {days} 天）："
        return ToolResult(
            textResultForLlm=header + "\n" + "\n".join(lines),
            resultType="success",
        )

    available = "、".join(f"「{s}」" for s in sources) if sources else "無"

    return ToolDefinition(
        name="query_observations",
        description=(
            "查詢 observation group 收集的背景知識。"
            "這是 compatibility path；優先使用 list_observation_candidates + "
            "query_observation_member。"
            "可查詢請假、進料、出料、工程進度等分類。"
            f"可用 group：{available}。"
            "category: 分類過濾（選填）。"
            "days: 往回看幾天（預設 7）。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "group": {
                    "type": "string",
                    "description": "observation group 名稱",
                },
                "category": {
                    "type": "string",
                    "description": "分類過濾（選填）",
                },
                "days": {
                    "type": "integer",
                    "description": "往回看幾天（預設 7）",
                },
            },
            "required": ["group"],
        },
        handler=handler,
        access_level=AccessLevel.GLOBAL,
    )
