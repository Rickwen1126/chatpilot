"""Browser tools — CDP-based browser control via iso-browser Chrome."""

from __future__ import annotations

import asyncio
import json
import logging
import os

from copilot.types import ToolInvocation, ToolResult

from chatpilot.core.types import AccessLevel, ToolDefinition

logger = logging.getLogger(__name__)

ISO_BROWSER_DIR = os.environ.get(
    "ISO_BROWSER_DIR",
    os.path.expanduser("~/.claude/skills/iso-browser"),
)
REGISTRY_PATH = os.path.expanduser("~/.iso-browser-chrome/registry.json")

# Module-level cached port
_chrome_port: str | None = None


async def _ensure_chrome() -> str:
    """Get CDP port, starting Chrome if needed. Caches result."""
    global _chrome_port
    if _chrome_port and _is_pid_alive_for_port(_chrome_port):
        return _chrome_port

    # Check registry
    if os.path.exists(REGISTRY_PATH):
        try:
            with open(REGISTRY_PATH) as f:
                registry = json.load(f)
            for port, info in registry.get("allocations", {}).items():
                pid = info.get("pid")
                if pid and _is_pid_alive(pid):
                    _chrome_port = str(port)
                    logger.info("Found Chrome on port %s", _chrome_port)
                    return _chrome_port
        except Exception:
            pass

    # Start new
    start_script = os.path.join(ISO_BROWSER_DIR, "scripts", "start.js")
    proc = await asyncio.create_subprocess_exec(
        "node", start_script,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    _chrome_port = stdout.decode().strip().split("\n")[0]
    logger.info("Started Chrome on port %s", _chrome_port)
    return _chrome_port


def _is_pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (OSError, TypeError):
        return False


def _is_pid_alive_for_port(port: str) -> bool:
    if not os.path.exists(REGISTRY_PATH):
        return False
    try:
        with open(REGISTRY_PATH) as f:
            registry = json.load(f)
        info = registry.get("allocations", {}).get(port, {})
        pid = info.get("pid")
        return _is_pid_alive(pid) if pid else False
    except Exception:
        return False


async def _run_script(script: str, *args: str) -> str:
    port = await _ensure_chrome()
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
        raise RuntimeError(f"{script} failed: {err}")
    return stdout.decode()


# ── Tool: browser_navigate ──────────────────────────────────────


def create_browser_navigate_tool() -> ToolDefinition:
    async def handler(invocation: ToolInvocation) -> ToolResult:
        args = invocation.get("arguments") or {}
        url = args.get("url", "")
        new_tab = args.get("new_tab", True)

        if not url:
            return ToolResult(
                textResultForLlm="需要提供 url",
                resultType="failure",
            )
        try:
            extra = ["--new"] if new_tab else []
            await _run_script("nav.js", url, *extra)
            await asyncio.sleep(1.5)
            # Return page title for confirmation
            title = await _run_script("eval.js", "document.title")
            return ToolResult(
                textResultForLlm=f"已開啟：{title.strip()}",
                resultType="success",
            )
        except Exception as e:
            return ToolResult(
                textResultForLlm=f"導航失敗: {e}",
                resultType="failure",
            )

    return ToolDefinition(
        name="browser_navigate",
        description=(
            "用瀏覽器開啟網頁。提供 URL，會用真實 Chrome 載入。"
            "Chrome 會自動啟動（不需手動）。"
            "搭配 browser_eval 可在頁面上執行 JS 提取資料。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "要開啟的網址",
                },
                "new_tab": {
                    "type": "boolean",
                    "description": "是否開新分頁（預設 true）",
                },
            },
            "required": ["url"],
        },
        handler=handler,
        access_level=AccessLevel.GLOBAL,
    )


# ── Tool: browser_eval ──────────────────────────────────────────


def create_browser_eval_tool() -> ToolDefinition:
    async def handler(invocation: ToolInvocation) -> ToolResult:
        args = invocation.get("arguments") or {}
        js = args.get("js", "")

        if not js:
            return ToolResult(
                textResultForLlm="需要提供 JavaScript 程式碼",
                resultType="failure",
            )
        try:
            output = await _run_script("eval.js", js)
            result = output.strip()
            if len(result) > 3000:
                result = result[:3000] + "\n...(truncated)"
            return ToolResult(
                textResultForLlm=result or "(empty)",
                resultType="success",
            )
        except Exception as e:
            return ToolResult(
                textResultForLlm=f"JS 執行失敗: {e}",
                resultType="failure",
            )

    return ToolDefinition(
        name="browser_eval",
        description=(
            "在目前瀏覽器頁面執行 JavaScript 並回傳結果。"
            "用於提取頁面資料、點擊元素、填表單等。"
            "多行程式碼請用 IIFE：'(() => { ... })()'。"
            "搭配 browser_navigate 先開啟目標頁面。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "js": {
                    "type": "string",
                    "description": "要執行的 JavaScript（單一表達式或 IIFE）",
                },
            },
            "required": ["js"],
        },
        handler=handler,
        access_level=AccessLevel.GLOBAL,
    )


# ── Tool: browser_tabs ──────────────────────────────────────────


def create_browser_tabs_tool() -> ToolDefinition:
    async def handler(invocation: ToolInvocation) -> ToolResult:
        args = invocation.get("arguments") or {}
        focus = args.get("focus")

        try:
            if focus is not None:
                await _run_script("focus.js", str(focus))
                return ToolResult(
                    textResultForLlm=f"已切換到分頁 {focus}",
                    resultType="success",
                )
            output = await _run_script("tabs.js")
            return ToolResult(
                textResultForLlm=output.strip() or "沒有分頁",
                resultType="success",
            )
        except Exception as e:
            return ToolResult(
                textResultForLlm=f"分頁操作失敗: {e}",
                resultType="failure",
            )

    return ToolDefinition(
        name="browser_tabs",
        description=(
            "列出瀏覽器分頁，或切換到指定分頁。"
            "不帶 focus → 列出所有分頁（* 標示目前分頁）。"
            "帶 focus → 切換到該分頁（數字索引或標題關鍵字）。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "focus": {
                    "type": "string",
                    "description": "切換目標（索引數字或標題關鍵字，選填）",
                },
            },
        },
        handler=handler,
        access_level=AccessLevel.GLOBAL,
    )
