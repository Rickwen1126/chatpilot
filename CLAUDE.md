# chatpilot Development Guidelines

Auto-generated from all feature plans. Last updated: 2026-03-03

## Active Technologies
- Python 3.11+ + FastAPI, Pydantic v2, github-copilot-sdk, line-bot-sdk, watchdog, pyyaml, uvicorn (002-new-mvp)
- In-memory（MVP）；SQLite（task history）；disk JSON（context buffer cold layer） (002-new-mvp)

- Python 3.11+ / FastAPI / uv (001-agent-gateway-mvp)

## Project Structure

```text
src/chatpilot/
tests/
config/
```

## Commands

uv run pytest && uv run ruff check src/

## Code Style

Python 3.11+: Pydantic v2 models, Protocol for interfaces, async/await, ruff formatting

## Recent Changes
- 002-new-mvp: Added Python 3.11+ + FastAPI, Pydantic v2, github-copilot-sdk, line-bot-sdk, watchdog, pyyaml, uvicorn

- 001-agent-gateway-mvp: Switched from TypeScript to Python 3.11+ / FastAPI / uv

## Copilot SDK Best Practices

- Tool 定義必須使用 SDK 的 `copilot.types.Tool` dataclass，不可用 plain dict
- Tool handler 必須遵守 SDK signature：`(ToolInvocation) -> ToolResult | Awaitable[ToolResult]`
- 參數從 `invocation["arguments"]` 取，不可自訂 handler signature
- Session config 的 `tools` 欄位接受 `list[Tool]`，可搭配 `copilot.define_tool()` 建立
- SDK 型別參考：`copilot.types` 的 Tool, ToolInvocation, ToolResult, SessionConfig

<!-- MANUAL ADDITIONS START -->
<!-- MANUAL ADDITIONS END -->
