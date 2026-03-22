"""web_search tool — search the web via DuckDuckGo HTML."""

from __future__ import annotations

import logging
import re
import urllib.parse
import urllib.request
from typing import Any

from pydantic import BaseModel, Field

from chatpilot.core.types import AccessLevel, ToolDefinition

logger = logging.getLogger(__name__)

DDGO_HTML_URL = "https://html.duckduckgo.com/html/"


class WebSearchParams(BaseModel):
    query: str = Field(description="搜尋關鍵字")


def create_web_search_tool() -> ToolDefinition:
    """Create a web search tool using DuckDuckGo HTML search."""

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
            results = await _search_ddg(query)
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


async def _search_ddg(query: str) -> str:
    """Search DuckDuckGo HTML and parse results."""
    import asyncio

    def _fetch() -> str:
        data = urllib.parse.urlencode({"q": query}).encode("utf-8")
        req = urllib.request.Request(
            DDGO_HTML_URL,
            data=data,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/125.0.0.0 Safari/537.36"
                ),
                "Content-Type": "application/x-www-form-urlencoded",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.read().decode("utf-8")

    html = await asyncio.to_thread(_fetch)
    return _parse_ddg_html(html, query)


def _parse_ddg_html(html: str, query: str) -> str:
    """Parse DuckDuckGo HTML results page."""
    results: list[dict[str, str]] = []

    # DuckDuckGo HTML results are in <div class="result"> blocks
    blocks = re.findall(
        r'<div class="[^"]*result[^"]*".*?</div>\s*</div>',
        html,
        re.DOTALL,
    )

    for block in blocks[:7]:
        # Extract title from <a class="result__a">
        title_match = re.search(
            r'<a[^>]*class="result__a"[^>]*>(.*?)</a>', block, re.DOTALL
        )
        # Extract snippet from <a class="result__snippet">
        snippet_match = re.search(
            r'class="result__snippet"[^>]*>(.*?)</a>', block, re.DOTALL
        )
        # Extract URL from <a class="result__url">
        url_match = re.search(
            r'<a[^>]*class="result__url"[^>]*href="([^"]*)"', block
        )

        if not title_match:
            continue

        title = re.sub(r"<[^>]+>", "", title_match.group(1)).strip()
        snippet = ""
        if snippet_match:
            snippet = re.sub(r"<[^>]+>", "", snippet_match.group(1)).strip()
        url = ""
        if url_match:
            raw = url_match.group(1)
            # DuckDuckGo wraps URLs in redirect, extract actual URL
            actual = re.search(r"uddg=([^&]+)", raw)
            if actual:
                url = urllib.parse.unquote(actual.group(1))
            else:
                url = raw

        if title:
            results.append({"title": title, "snippet": snippet, "url": url})

    if not results:
        return f"No results found for '{query}'."

    lines: list[str] = []
    for i, r in enumerate(results[:5], 1):
        lines.append(f"{i}. **{r['title']}**")
        if r["snippet"]:
            lines.append(f"   {r['snippet']}")
        if r["url"]:
            lines.append(f"   {r['url']}")
    return "\n".join(lines)
