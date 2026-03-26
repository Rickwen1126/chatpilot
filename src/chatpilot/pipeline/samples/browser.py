"""Browser pipeline — web browsing via iso-browser Chrome CDP."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import urllib.parse

from chatpilot.core.types import NodeOutput
from chatpilot.pipeline.executor import PipelineDefinition
from chatpilot.pipeline.node import PipelineNode

logger = logging.getLogger(__name__)

ISO_BROWSER_DIR = os.environ.get(
    "ISO_BROWSER_DIR",
    os.path.expanduser("~/.claude/skills/iso-browser"),
)
REGISTRY_PATH = os.path.expanduser("~/.iso-browser-chrome/registry.json")


class BrowserSearchNode:
    """Searches Google via real Chrome (iso-browser CDP)."""

    @property
    def name(self) -> str:
        return "browser-search"

    async def execute(self, input: dict) -> NodeOutput:
        query = input.get("description", input.get("query", ""))
        if not query:
            return NodeOutput(status="error", data={}, error="No query provided")

        try:
            port = await self._get_port()

            # Navigate to Google search
            encoded = urllib.parse.quote(query)
            url = f"https://www.google.com/search?q={encoded}&hl=zh-TW"
            await self._run_script(port, "nav.js", url, "--new")

            # Wait for page load
            await asyncio.sleep(2)

            # Extract results via eval
            js = """(() => {
                const results = [];
                document.querySelectorAll('a:has(h3)').forEach((a, i) => {
                    if (i >= 7) return;
                    const h3 = a.querySelector('h3');
                    const parent = a.closest('[data-hveid]');
                    let snippet = '';
                    if (parent) {
                        const spans = parent.querySelectorAll('span:not(:has(*))');
                        for (const s of spans) {
                            if (s.innerText.length > 30) {
                                snippet = s.innerText.substring(0, 200); break;
                            }
                        }
                    }
                    results.push({ title: h3.innerText, url: a.href, snippet: snippet });
                });
                return JSON.stringify(results);
            })()"""

            output = await self._run_script(port, "eval.js", js)
            results = json.loads(output.strip()) if output.strip() else []

            return NodeOutput(
                status="success",
                data={"results": results, "query": query},
            )
        except Exception as e:
            logger.exception("Browser search failed")
            return NodeOutput(status="error", data={}, error=str(e))

    async def _get_port(self) -> str:
        """Get CDP port: read registry for existing, or start new Chrome."""
        # Check registry for running instance
        if os.path.exists(REGISTRY_PATH):
            try:
                with open(REGISTRY_PATH) as f:
                    registry = json.load(f)
                ports = registry.get("ports", {})
                for port, info in ports.items():
                    pid = info.get("pid")
                    if pid and self._is_pid_alive(pid):
                        logger.info("Found running Chrome on port %s", port)
                        return str(port)
            except Exception:
                pass

        # No running instance — start one (auto-assign port)
        start_script = os.path.join(ISO_BROWSER_DIR, "scripts", "start.js")
        proc = await asyncio.create_subprocess_exec(
            "node", start_script,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        port = stdout.decode().strip().split("\n")[0]
        logger.info("Started Chrome on port %s", port)
        return port

    @staticmethod
    def _is_pid_alive(pid: int) -> bool:
        try:
            os.kill(pid, 0)
            return True
        except (OSError, TypeError):
            return False

    async def _run_script(self, port: str, script: str, *args: str) -> str:
        """Run an iso-browser script and return stdout."""
        script_path = os.path.join(ISO_BROWSER_DIR, "scripts", script)
        cmd = ["node", script_path, "--port", port, *args]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            err = stderr.decode().strip()
            logger.warning("Script %s failed: %s", script, err)
        return stdout.decode()


class BrowserPipeline(PipelineDefinition):
    """Browser search pipeline via real Chrome."""

    name = "browser-search"

    def __init__(self) -> None:
        self.nodes: list[PipelineNode] = [BrowserSearchNode()]
        self.max_iterations = 1
