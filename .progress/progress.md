## 2026-03-22 10:20 — v2 Implementation + CodeTour + Code Review 完成

**Goal**: 實作 v2 全部 42 tasks，建立架構 CodeTour，code review 修 bug

**Done**:
- `/speckit.implement` 完成：9 phases, 42 tasks, 32 source files, 2259 LOC
- CodeTour `.tours/01-architecture-chatpilot-v2.tour`：Sky Eye 7 stops，追蹤 chat + async task 兩條 data flow
- Code review 兩輪，修了 10+ issues（見下方 Decisions）
- 23 tests passing, ruff clean
- Commit `d13a6c5`, `9c283f2`
- SDK integration 修正：用 SDK 原生 `send_and_wait`，修 system_message 格式、session ID 冒號問題
- E2E mock test 通過：webhook → mock adapter → hub → router → chatbot → SDK → response（gpt-5-mini, 7 秒回覆）
- Tour 過程中發現 + 修復 critical issues（tool handler 斷路、busy mention buffer、AccessLevel 合併）
- LINE adapter fix：`MentionTarget` → `UserMentionee`（linebot SDK v3 API 差異）
- LINE E2E 通過：私聊「測試 123」→ bot 回覆（gpt-5-mini, 7 秒）
- 3 chatbot personas：gossip-king (gpt-4.1)、scholar (gpt-5-mini)、senior-scholar (gpt-5.4-mini)
- web_search tool：DuckDuckGo HTML 搜尋（取代 API 版，中文 + 即時新聞可用）
- browse_task tool + BrowserPipeline：Playwright headless 異步搜尋（AGENT_TEAM_TRIGGER）
- LINE 長文分段 push（5000 chars/chunk，5 msgs/call）
- `/chatbot list` 子指令 + 群組 slash command 需 @bot
- LINE reply token 過期 fallback push（25s buffer）
- Commits: `d13a6c5` ~ `6403c3c`

**Decisions**:
- Hub busy/idle race：`set_busy` 移到 `create_task` 之前
- `/model` 不 mutate shared ChatbotConfig：改用 `_route_model_overrides` per-route dict（in-memory，重啟丟失 — 記在 plan.md Open Questions）
- Busy 時 mention 不存 buffer，直接拒絕 + 回「處理中」。原因：使用者不知道 buffer 訊息會變成下次的 context
- Tool 必須用 SDK `copilot.types.Tool` dataclass，不是 plain dict（之前用錯了）。Handler 必須遵守 `(ToolInvocation) -> ToolResult` signature
- `mark_agent_team_tool` 合併進 `AccessLevel.AGENT_TEAM_TRIGGER = 4`，type contract 取代 runtime flag
- Chatbot timeout 改為 config 可設（`ChatbotConfig.timeout`），timeout/crash 時 destroy session + mark broken，下次自動重建
- Task timeout 用 `asyncio.wait_for` 包 pipeline execution
- Runner persist 失敗不 block push（try/except 分離）
- Runner shutdown 改 `asyncio.Event` 取代 1 秒 polling
- Router 同分：`>=` last-defined-wins，加文件說明
- Copilot SDK best practices 加入 CLAUDE.md
- SDK 原生 send_and_wait 取代自製 event listener
- system_message 必須用 `mode: "replace"`（不是 append）。append 會保留 Copilot CLI 的 agent system prompt + built-in tools，導致 Claude 模型跑 agent loop 掃檔案
- session ID 冒號問題：route_id 的 `:` 改成 `-`（SDK 不接受冒號）

**State**: Branch `002-new-mvp`, commit `6403c3c`. 23 tests, ruff clean. LINE E2E 驗證通過（八卦王 + web search + reply fallback push）。

**Next**:
- [ ] 群組 @bot mention 測試（驗證 mention filter + context buffer）
- [ ] 連發兩則測 busy gate
- [ ] `/model`、`/chatbot` 切換 LINE 實測
- [ ] CLI adapter 補做（US3：目前 cli/main.py 繞過 server）
- [ ] `lifespan()` 160+ 行，可拆分但不急
- [ ] per-route model override 持久化（plan.md Open Questions）

**User Notes**:
- 查看下一步
- E2E mock test 通過，LINE adapter 還需要 debug
- Claude 模型在 Copilot CLI 會跑 agent loop 很慢，用 gpt-5-mini 測試秒回。GPT-4.1 疑似當機（0x 是免費不是不可用）
- 要補做原生 CLI tool（spec US3 的 adapter，目前 cli/main.py 繞過 server 直接呼叫 ChatbotManager）
- LINE E2E 通過，v2 MVP 完整驗證完成
- tunnel 設定在 `~/.cloudflared/config.yaml`：`bot.webric.dev` → `localhost:2999`
- 3 chatbot + web search + browser pipeline + LINE 分段 + slash command gate 完成
- SDK `list_models()` 不列出所有 model，但直接用 model ID 字串可以跑（gpt-5.4, gpt-5.4-mini 都可用）
- DuckDuckGo HTML 版比 API 版好很多，中文即時新聞都搜得到
- LINE 回覆 2964 chars 走 push（reply token 54s 過期），分段邏輯就位但實際很少觸發（<5000 chars）

---

## 2026-03-21 11:13 — v2 Plan + Tasks 完成，ready to implement

**Goal**: 基於 v2 spec 產出完整實作計畫（plan → research → data model → contracts → tasks），解決所有待決事項，通過 cross-artifact 分析。

**Done**:
- `/speckit.plan` 完成：Technical Context、Constitution Check（7/7 pass）、Project Structure（10 packages）
- Phase 0 research.md：10 項 spec 待決事項全部解決（SDK error handling、SQLite task history、uuid4、context buffer 結構化格式、queue backpressure、memory tool JSON、completion_condition callable、node output 格式）
- Phase 1 data-model.md：12 個核心實體 + 關係圖 + 持久化策略
- Phase 1 contracts/：6 個 Protocol 契約（adapter, message-hub, tool-factory, scheduler, pipeline, webhook-api）
- Phase 1 quickstart.md
- `/ship` Technical Context review：全 [N]，零 Block，可開工
- `/speckit.tasks` 完成：42 tasks, 9 phases, 6 user stories
- `/speckit.analyze` 完成：8 findings（2 HIGH + 4 MEDIUM + 2 LOW），2 HIGH 已修復，1 MEDIUM (F3) 已修復
- v1 code reusability：~35% keep, ~40% refactor, ~25% replace

**Decisions**:
- SDK 共用單一 CLI process，多 session 共用（已驗證）
- Context buffer 注入方式：串接 user message 前面（SDK 無 context API）
- `/model` 切換：prefix command 解析（在 hub 層攔截），不送進 chatbot session。ChatbotManager destroy + recreate session with new model
- Hub 用 callback pattern：`on_proceed(message, context_prefix, adapter)` + `on_command(command, args, message, adapter)`。Hub 不持有 router/chatbot reference，只管 gate + context
- Task history：SQLite WAL mode（`data/tasks.db`）
- Memory Tool：JSON files（`data/memory/{task_id}/`）
- Queue backpressure：max_queue_size config + reject
- aiosqlite 加入依賴

**State**: Branch `002-new-mvp`。所有設計文件完成，analyze 通過。未開始實作。

**Next**:
- [ ] `/speckit.implement` — 開始實作 42 tasks
- [ ] 建議順序：Phase 1 (Setup) → Phase 2 (Foundational) → Phase 3 (US1 MVP) → Phase 4 (US2)
