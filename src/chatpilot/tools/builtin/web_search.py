"""web_search tool — search the web via DuckDuckGo."""

from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
from typing import Any

from pydantic import BaseModel, Field

from chatpilot.core.types import AccessLevel, ToolDefinition

logger = logging.getLogger(__name__)

DDGO_URL = "https://api.duckduckgo.com/"


class WebSearchParams(BaseModel):
    query: str = Field(description="搜尋關鍵字")


def create_web_search_tool() -> ToolDefinition:
    """Create a web search tool using DuckDuckGo Instant Answer API."""

    async def handler(invocation: Any) -> Any:
        from copilot.types import ToolResult

        args = invocation.get("arguments") or {}
        query = args.get("query", "")
        if not query:
            return ToolResult(
                textResultForLlm="請提供搜尋關鍵字",
                resultType="failure",
            )

        try:
            results = await _search(query)
            return ToolResult(
                textResultForLlm=results,
                resultType="success",
            )
        except Exception as e:
            logger.error("Web search failed: %s", e)
            return ToolResult(
                textResultForLlm=f"搜尋失敗: {e}",
                resultType="failure",
            )

    return ToolDefinition(
        name="web_search",
        description="搜尋網路資訊。提供關鍵字，回傳搜尋結果摘要。",
        parameters=WebSearchParams.model_json_schema(),
        handler=handler,
        access_level=AccessLevel.GLOBAL,
    )


async def _search(query: str) -> str:
    """Search DuckDuckGo and return formatted results."""
    import asyncio

    def _fetch() -> dict:
        params = urllib.parse.urlencode({
            "q": query, "format": "json", "no_html": "1", "skip_disambig": "1"
        })
        url = f"{DDGO_URL}?{params}"
        req = urllib.request.Request(url, headers={"User-Agent": "ChatPilot/0.2"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))

    data = await asyncio.to_thread(_fetch)

    lines: list[str] = []

    # Abstract (main answer)
    if data.get("AbstractText"):
        lines.append(f"## {data.get('AbstractSource', 'Result')}")
        lines.append(data["AbstractText"])
        if data.get("AbstractURL"):
            lines.append(f"Source: {data['AbstractURL']}")

    # Related topics
    for topic in (data.get("RelatedTopics") or [])[:5]:
        if isinstance(topic, dict) and topic.get("Text"):
            text = topic["Text"][:200]
            url = topic.get("FirstURL", "")
            lines.append(f"- {text}")
            if url:
                lines.append(f"  {url}")

    if not lines:
        lines.append(f"No direct results for '{query}'. Try rephrasing.")

    return "\n".join(lines)
