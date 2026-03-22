# chatpilot Development Guidelines

Last updated: 2026-03-22

## Active Technologies
- Python 3.11+ + FastAPI, Pydantic v2, github-copilot-sdk, line-bot-sdk, watchdog, pyyaml, uvicorn, playwright
- Storage: In-memory（MVP）；SQLite（task history）；disk JSON（context buffer cold layer）
- Python 3.11+（沿用既有） + FastAPI, Pydantic v2, aiosqlite, github-copilot-sdk（全部既有） (003-memory-scheduler)
- SQLite（複用 TaskStore 的 aiosqlite + WAL 模式） (003-memory-scheduler)

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

## Specs
- `specs/` — 現行規格（spec.md, plan.md, tasks.md, contracts/, data-model.md）
- `specs/archive/` — 舊版規格（001-agent-gateway-mvp）

## Copilot SDK Best Practices

- Tool 定義必須使用 SDK 的 `copilot.types.Tool` dataclass，不可用 plain dict
- Tool handler 必須遵守 SDK signature：`(ToolInvocation) -> ToolResult | Awaitable[ToolResult]`
- 參數從 `invocation["arguments"]` 取，不可自訂 handler signature
- Session config 的 `tools` 欄位接受 `list[Tool]`，可搭配 `copilot.define_tool()` 建立
- SDK 型別參考：`copilot.types` 的 Tool, ToolInvocation, ToolResult, SessionConfig
- `system_message` 必須用 `mode: "replace"`，不可用 `append`（append 會保留 CLI agent 的 built-in tools）
- `list_models()` 不一定列出所有可用 model，可直接用 model ID 字串嘗試

## Adapter 開發規範

- 新增 adapter 必須實作 `ChannelAdapter` Protocol 的所有方法
- 必須定義 `format_hint` property：平台有格式限制時回傳提示字串（如 LINE 不支援 Markdown），無限制回傳 None
- `format_hint` 會自動注入 chatbot 的 prompt，讓 LLM 遵守平台格式限制
- 長文回覆必須處理平台字數上限（如 LINE 5000 chars/msg，分段 push）
- Reply 機制有時效限制時（如 LINE reply token 30s），需實作 fallback 到 push
- 必須實作 `download_media(media_id) -> bytes | None`，讓 `download_media` tool 可跨平台下載媒體

## 平台已知問題與解法

### LINE
- **Markdown 不支援**：`format_hint` 注入「不使用 Markdown」指令，LLM 自動遵守
- **Reply token 30s 過期**：`send_reply` 檢查 elapsed > 25s 自動 fallback 到 `push_message`
- **@Bot mention 偵測**：linebot SDK v3 用 `UserMentionee.is_self`（snake_case），不是 `isSelf`（camelCase）
- **群組 @Bot /command**：LINE 把 `@Bot` 放在 text 前面，Hub 用 `re.sub(r"^@\S+\s+", "")` strip 後檢查 `/` 前綴
- **圖片處理**：parser 產出 `[圖片 ref:line:{message_id}]` 作為 text 存入 context buffer，LLM 需要時呼叫 `download_media` tool 下載。圖片不預先展開，ref 只是文字，LLM 自主決定是否下載
- **長文分段**：5000 chars/msg 上限，自動切 chunk，reply 最多 5 則，超過用 push 分批送

## Tool 開發流程

1. 在 `src/chatpilot/tools/builtin/` 建立模組
2. 定義 Pydantic model 做 params schema（用 `.model_json_schema()` 產 JSON Schema）
3. Handler 遵守 SDK signature：`async handler(invocation: ToolInvocation) -> ToolResult`
4. 用 `ToolDefinition` 包裝，設定 `AccessLevel`：
   - `GLOBAL`：chatbot + pipeline 都能用（如 web_search）
   - `CHATBOT_ONLY`：僅 chatbot（如 task_history）
   - `AGENT_TEAM_TRIGGER`：chatbot 可呼叫但 pipeline 禁用（如 submit_task、browse_task）
5. 在 `server/__init__.py` 的 lifespan 中 `tool_factory.register()`
6. 在 chatbot config 的 `tools` 列表加入 tool name

## Agent Team Pipeline 開發流程

1. 在 `src/chatpilot/pipeline/samples/` 建立 pipeline 模組
2. 實作 `PipelineNode` Protocol（`name` property + `async execute(input) -> NodeOutput`）
3. 繼承 `PipelineDefinition`，設定 `name` 和 `nodes` 列表
4. 在 `server/__init__.py` 的 lifespan 中 `pipeline_executor.register()`
5. 建立對應的 `AGENT_TEAM_TRIGGER` tool 讓 chatbot 可觸發

<!-- MANUAL ADDITIONS START -->
<!-- MANUAL ADDITIONS END -->

## Recent Changes
- 003-memory-scheduler: Added Python 3.11+（沿用既有） + FastAPI, Pydantic v2, aiosqlite, github-copilot-sdk（全部既有）
