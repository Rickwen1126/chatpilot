"""quote_search tool — search historical paint quotes for Shinyipaint."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from copilot.types import ToolInvocation, ToolResult

from chatpilot.core.types import AccessLevel, ToolDefinition

logger = logging.getLogger(__name__)

DATA_FILE = Path(__file__).resolve().parents[4] / "data" / "quotes" / "quotes.json"


def _load_quotes() -> list[dict[str, Any]]:
    """Load quotes from JSON file."""
    if not DATA_FILE.exists():
        logger.warning("Quotes data file not found: %s", DATA_FILE)
        return []
    with open(DATA_FILE, encoding="utf-8") as f:
        return json.load(f)


def _search(
    quotes: list[dict[str, Any]],
    *,
    keyword: str | None = None,
    building_type: str | None = None,
    min_area: float | None = None,
    max_area: float | None = None,
    brand: str | None = None,
) -> list[dict[str, Any]]:
    """Filter quotes by AND conditions."""
    results = quotes

    if building_type:
        results = [q for q in results if q.get("building_type") == building_type]

    if min_area is not None:
        results = [q for q in results if q.get("area_ping", 0) >= min_area]

    if max_area is not None:
        results = [q for q in results if q.get("area_ping", 0) <= max_area]

    if brand:
        results = [q for q in results if brand in q.get("paint_brand", "")]

    if keyword:
        kw = keyword.lower()
        results = [
            q
            for q in results
            if kw in q.get("project_name", "").lower()
            or kw in q.get("paint_type", "").lower()
            or kw in q.get("notes", "").lower()
        ]

    return results


def create_quote_search_tool() -> ToolDefinition:
    """Create quote_search tool for historical quote lookup."""

    async def handler(invocation: ToolInvocation) -> ToolResult:
        args = invocation.get("arguments") or {}
        keyword = args.get("keyword")
        building_type = args.get("building_type")
        min_area = args.get("min_area")
        max_area = args.get("max_area")
        brand = args.get("brand")

        try:
            quotes = _load_quotes()
            results = _search(
                quotes,
                keyword=keyword,
                building_type=building_type,
                min_area=min_area,
                max_area=max_area,
                brand=brand,
            )

            # Cap at 10 most recent
            results = sorted(results, key=lambda q: q.get("date", ""), reverse=True)[
                :10
            ]

            if not results:
                return ToolResult(
                    textResultForLlm="找不到符合條件的歷史報價紀錄",
                    resultType="success",
                )

            return ToolResult(
                textResultForLlm=json.dumps(results, ensure_ascii=False, indent=2),
                resultType="success",
            )
        except Exception as e:
            logger.error("Quote search failed: %s", e)
            return ToolResult(
                textResultForLlm=f"報價搜尋失敗: {e}",
                resultType="failure",
            )

    return ToolDefinition(
        name="quote_search",
        description=(
            "搜尋歷史報價紀錄。"
            "可依建案類型（住宅/商辦/廠房）、坪數範圍、油漆品牌篩選。"
            "回傳匹配的歷史報價資料，供整理比較報告。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "keyword": {
                    "type": "string",
                    "description": "搜尋關鍵字（案名、品牌、備註等）",
                },
                "building_type": {
                    "type": "string",
                    "enum": ["住宅", "商辦", "廠房"],
                    "description": "建案類型篩選",
                },
                "min_area": {
                    "type": "number",
                    "description": "最小坪數",
                },
                "max_area": {
                    "type": "number",
                    "description": "最大坪數",
                },
                "brand": {
                    "type": "string",
                    "description": "油漆品牌篩選（如：虹牌、立邦、得利）",
                },
            },
            "required": [],
        },
        handler=handler,
        access_level=AccessLevel.GLOBAL,
    )
