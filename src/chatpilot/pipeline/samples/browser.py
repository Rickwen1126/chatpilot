"""Browser pipeline — web browsing via headless Chromium."""

from __future__ import annotations

import logging

from playwright.async_api import async_playwright

from chatpilot.core.types import NodeOutput
from chatpilot.pipeline.executor import PipelineDefinition
from chatpilot.pipeline.node import PipelineNode

logger = logging.getLogger(__name__)


class BrowserSearchNode:
    """Searches Google and extracts results using headless browser."""

    @property
    def name(self) -> str:
        return "browser-search"

    async def execute(self, input: dict) -> NodeOutput:
        query = input.get("description", input.get("query", ""))
        if not query:
            return NodeOutput(status="error", data={}, error="No query provided")

        try:
            results = await self._search(query)
            return NodeOutput(status="success", data={"results": results, "query": query})
        except Exception as e:
            logger.exception("Browser search failed")
            return NodeOutput(status="error", data={}, error=str(e))

    async def _search(self, query: str) -> list[dict]:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                page = await browser.new_page(
                    user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
                )
                await page.goto(
                    f"https://www.google.com/search?q={query}&hl=zh-TW",
                    wait_until="domcontentloaded",
                    timeout=15000,
                )
                # Extract search results
                results = []
                items = await page.query_selector_all("div.g")
                for item in items[:5]:
                    title_el = await item.query_selector("h3")
                    snippet_el = await item.query_selector("[data-sncf], .VwiC3b")
                    link_el = await item.query_selector("a")
                    title = await title_el.inner_text() if title_el else ""
                    snippet = await snippet_el.inner_text() if snippet_el else ""
                    href = await link_el.get_attribute("href") if link_el else ""
                    if title:
                        results.append({"title": title, "snippet": snippet, "url": href})
                return results
            finally:
                await browser.close()


class BrowserPipeline(PipelineDefinition):
    """Browser search pipeline for agent team async tasks."""

    name = "browser-search"

    def __init__(self) -> None:
        self.nodes: list[PipelineNode] = [BrowserSearchNode()]
        self.max_iterations = 1
