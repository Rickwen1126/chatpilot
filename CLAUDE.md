# chatpilot Development Guidelines

Last updated: 2026-03-26

## Development Cycle (必須遵守)

每個功能實作必須完成以下循環，不得跳步：

```
1. 實作功能
2. uv run ruff check src/ && uv run pytest tests/  （unit test 通過）
3. bash tests/e2e/run_e2e.sh  （既有 E2E 不壞）
4. 新功能 E2E 測試（四層驗證標準）：
   - L1 Response — 有回覆、非錯誤
   - L2 Tool call — grep log `[tool_call]` 確認正確 tool 被呼叫
   - L3 Side effect — sqlite3 query 確認 DB state 正確改變
   - L4 Intent — 功能完整走完（reminder 推播、schedule 連續觸發、observer entries 可追溯）
   - 每項新功能 E2E 至少 L3，關鍵功能 L4
5. 遇到問題 → 修復 → 回到 step 2 重跑
6. 全部通過 → 新功能測試項目寫入 /e2e checklist
7. commit
8. Milestone review（每個 milestone 做一次）：
   - /codetour — 產生 CodeTour 紀錄改動脈絡
   - /reviewCode — code review 確認品質
   - 必須用 subagent (opus) 執行，避免上下文污染盲點
```

**不要**：
- 實作完就 commit 不測試
- 只跑 unit test 不跑 E2E
- E2E 只看 pass/fail 不看 log
- 新功能沒加入 /e2e checklist
- 改 schema/新增欄位後不檢查 DB 既有資料的影響（必要時做 migration 或清理舊資料）

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

## Admin API

管理群組/對話 binding 和標籤的 API：

```bash
# 列出所有已知 routes（含標籤、chatbot binding、sessions）
GET /cli/routes

# 從 LINE API 同步群組名稱+人數到標籤
POST /cli/routes/sync

# 手動設定/移除標籤
POST /cli/routes/label
  {"route_id": "line:Cxxx", "label": "群組名稱"}
  # label 空字串 = 移除

# 重新載入 config
POST /cli/reload
```

標籤存在 `data/route_labels.json`，重啟不會遺失。

## Copilot SDK Model 限制

- `list_models()` 不一定列出所有可用 model，可直接用 model ID 字串嘗試
- SDK 0.2.0 model list 不含 `gpt-5.4-mini`（CLI/VS Code 有）
- **Claude 全系列在 SDK 中不支援 `binaryResultsForLlm`**（tool 回傳圖片 binary data 會 timeout）
- Binary tool result 可用 model：gpt-4.1, gpt-5-mini, gpt-5.1, gpt-5.2, gpt-5.3-codex, gemini-3-pro-preview
- Binary tool result 不可用：claude-haiku-4.5, claude-sonnet-4.6, gpt-5.2-codex

## Hub 媒體處理

- 純媒體訊息（只有 `[圖片/音檔/檔案/影片 ref:...]`，沒有其他文字）→ 進 context buffer，不觸發 chatbot
- 使用者下一則文字訊息會 drain context buffer，chatbot 同時看到媒體 ref + 文字
- 這解決 LINE 私訊無法同時傳圖片+文字的問題

<!-- MANUAL ADDITIONS START -->
<!-- MANUAL ADDITIONS END -->

## Recent Changes
- 003-memory-scheduler: Added Python 3.11+（沿用既有） + FastAPI, Pydantic v2, aiosqlite, github-copilot-sdk（全部既有）
