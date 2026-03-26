"""query_observations tool — query observer data across chats."""

from __future__ import annotations

import logging
from typing import Any

from copilot.types import ToolInvocation, ToolResult

from chatpilot.core.types import AccessLevel, ToolDefinition

logger = logging.getLogger(__name__)


def create_query_observations_tool(
    memory_store: Any,
    observer_sources: dict[str, dict] | None = None,
) -> ToolDefinition:
    """Create query_observations tool.

    observer_sources: {
        "信益大群組": {
            "route_id": "line:Cxxx",
            "allowed_consumers": ["line:Ceead...", "line:Ufc68..."]
        }
    }
    """
    sources = observer_sources or {}

    async def handler(invocation: ToolInvocation) -> ToolResult:
        args = invocation.get("arguments") or {}
        session_id = invocation.get("session_id", "")
        caller_route = session_id.split("__")[0].replace("-", ":", 1)

        source_name = args.get("source", "")
        category = args.get("category", "")
        days = args.get("days", 7)

        if not source_name:
            available = list(sources.keys())
            return ToolResult(
                textResultForLlm=(
                    f"需要指定來源。可用：{', '.join(available)}"
                    if available
                    else "沒有設定觀察來源"
                ),
                resultType="failure",
            )

        # Resolve source
        src = sources.get(source_name)
        if src is None:
            # Try matching by route_id directly
            for name, cfg in sources.items():
                if cfg.get("route_id") == source_name:
                    src = cfg
                    break
        if src is None:
            return ToolResult(
                textResultForLlm=f"找不到來源「{source_name}」",
                resultType="failure",
            )

        # Permission check
        allowed = src.get("allowed_consumers", [])
        if allowed and caller_route not in allowed:
            return ToolResult(
                textResultForLlm="無權限查詢此來源的觀察資料",
                resultType="failure",
            )

        # Query all route_ids for this source
        all_routes = src.get("all_route_ids", [src["route_id"]])
        logger.info(
            "[query_obs] source=%s caller=%s routes=%s cat=%s days=%s",
            source_name, caller_route, all_routes, category, days,
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
                who = entry.get("who", "?")
                cat = entry.get("category", "")
                content = entry.get("content", "")
                ts = entry.get("timestamp", "")
                lines.append(f"• [{cat}] {who}: {content} ({ts})")
                total_entries += 1

        header = f"觀察紀錄（{source_name}，{total_entries} 筆"
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
            "查詢觀察者收集的群組資訊。"
            "可查詢請假、進料、出料、工程進度等分類。"
            f"可用來源：{available}。"
            "category: 分類過濾（選填）。"
            "days: 往回看幾天（預設 7）。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "source": {
                    "type": "string",
                    "description": "觀察來源名稱",
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
            "required": ["source"],
        },
        handler=handler,
        access_level=AccessLevel.GLOBAL,
    )
