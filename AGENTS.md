# chatpilot Development Guidelines

Last updated: 2026-04-08

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
6. 全部通過 → 新功能測試項目寫入 E2E checklist / specs 記錄
7. commit
8. Milestone review（每個 milestone 做一次）：
   - `codetour` — 產生 CodeTour 紀錄改動脈絡
   - `reviewCode` 或內建 code review — 確認品質
   - 需要獨立審查時，使用 subagent 做 second-pass review，避免上下文污染盲點
```

**不要**：
- 實作完就 commit 不測試
- 只跑 unit test 不跑 E2E
- E2E 只看 pass/fail 不看 log
- 新功能沒加入 E2E checklist / specs 記錄
- 改 schema/新增欄位後不檢查 DB 既有資料的影響（必要時做 migration 或清理舊資料）

## Repo-local Skills

- repo-local Claude commands 已鏡像成 Codex wrapper skills，放在 `.agents/skills/`
- 可直接使用 `e2e`、`observer_setup`、`speckit.*` 這些 repo-local skill 名稱
- 這些 wrapper 會讀對應的 `.claude/commands/*.md`，但會改用 Codex 的 tool / subagent / skill 流程

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

## Live Server Logging

- 手動啟動或重啟 live `localhost:2999` 做 debug / smoke / 實機驗證時，必須把 stdout/stderr 落到固定 log sink，預設使用 `/tmp/chatpilot-2999.log`
- 建議啟動方式：
  - `uv run uvicorn chatpilot.server:create_app --factory --host 0.0.0.0 --port 2999 > /tmp/chatpilot-2999.log 2>&1 &`
- 驗證 live 行為時，預設要能直接用 `tail -f /tmp/chatpilot-2999.log` 看到：
  - `[discovery]`
  - `[hub]`
  - `[observer]`
  - `[tool_call]`
  - `[tool_result]`
- 若不是用上述方式啟動，也必須提供等價的穩定 log sink；不可只靠 terminal 畫面暫時滾動輸出

## Logging Design Principles

- logging 是一等公民。新功能若跨 webhook / router / hub / observer / tool / scheduler / DB 邊界，但無法從 log 讀出主要 dataflow，視為未完成
- log 預設以單一 stream 思維設計；分類優先靠 `tag + level + key=value`，不是先靠拆多個檔案
- `route_id` 是 chatpilot log 的主關聯鍵；若有跨 route 行為，必須補 `target_route_id`
- 若事件與 Copilot SDK session 有關，應能從 log 串起：
  - `route_id`
  - `sdk_session_id`
  - `task_id` / `schedule_id`
  - `tool_name`
- 保留 Copilot SDK 原生日誌訊號。`[SDK]` / `[event]` 這類 session runtime log 是重要 debug 資產；chatpilot 應補 correlation，不應把它們過度抽象或改寫到失真
- INFO 寫 state transition，DEBUG 寫 decision detail，WARNING 寫 degraded/fallback，ERROR 寫 failed path；不要把關鍵狀態塞在 DEBUG，或把大量 payload 噪音塞在 INFO
- 重要 log 盡量包含：
  - `event`
  - `route_id`
  - `target_route_id`（若有）
  - `group` / `profile`（若有）
  - `chatbot`
  - `session_id` / `sdk_session_id`
  - `task_id` / `schedule_id`
  - `tool_name`
- 文字風格優先用「短描述 + key=value」，讓人可以直接 grep 與肉眼追 dataflow
- 寫 log 時避免整包敏感原文、token、secret；若需要 debug payload，優先寫 preview / summary / ref / id
- local logging 最終應由 app 內建 config 控制，不依賴 shell redirect 才能有可用 log；write-file 只是第一個 backend，未來可替換成其他 logging backend

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
- 設計 Copilot request 時，優先採用「單次大 request + 明確 rubric / todo / success criteria」模式，不要把同一個任務拆成大量一來一回的小 prompt
- 對 Copilot 而言，成本與穩定性重點更接近 request 次數，而不是 token；能在一次 request 內講清楚完整任務、驗證標準、預期 tool 使用與輸出格式時，應盡量一次講清楚
- 尤其是 schedule、自動 health check、批次匯入、multi-step semantic probe 這類任務，應優先把 probe queries、must-hit facts、forbidden drift、驗證步驟一起包進單次 request，讓 Copilot 一次規劃並執行

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
- **群組 @Bot /command**：LINE 把 `@Bot` 放在 text 前面，Hub 用 `re.sub(r"^@\\S+\\s+", "")` strip 後檢查 `/` 前綴
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
# 列出所有已知 routes（含標籤、chatbot binding、已知 chatbot；非 live session 清單）
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
