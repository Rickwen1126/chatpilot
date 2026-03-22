## 2026-03-22 23:31 — 003 spec 完成 + custom_prompt + 平台問題發現

**Goal**: Memory Store + Cron Scheduler spec/plan，加 custom_prompt type

**Done**:
- 003-memory-scheduler spec 加入 custom_prompt type（使用者偏好/習慣）
- Session needs_rebuild pattern 設計完成：custom_prompt 更新 → 標記 → 下則訊息重建 session
- Commit `ae0a5a3`

**Decisions**:
- custom_prompt 注入 system_message：session create 時合併，不是每輪注入
- needs_rebuild 複用 broken session eviction pattern，無 race condition（busy gate 序列化）
- Reminder 未來也走 pipeline 讓 chatbot 潤飾（MVP 先直接 push 原文）
- 圖床用 Cloudflare R2（免費 10GB/月 + 免費 egress），記在 plan.md Future Tasks
- 群組觸發關鍵字：`AI `（不分大小寫）+ `@bot mention` 並行，放 config 不放 adapter

**State**: Branch `003-memory-scheduler`, commit `ae0a5a3`. Spec/Plan/Research/DataModel/Contracts 全完成。待 `/speckit.tasks`。

**Next**:
- [ ] `/speckit.tasks` → 產出 tasks.md
- [ ] 實作 Memory Store + Cron Scheduler + custom_prompt
- [ ] 群組 trigger_keywords 功能（`routes.yaml` config-driven，跟 003 無關，獨立做）

**User Notes**:
- LINE 電腦版無法 @ bot（已知限制），需要關鍵字觸發作為替代方案
- 觸發方式設計：config `trigger_keywords: ["ai"]`，mention_filter.py 讀 config 檢查，全平台生效
- 這個跟 003 spec 無關，獨立處理

---

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

**State**: Branch `003-memory-scheduler`, commit `b48a456`. Spec + Plan + Research + Data Model + Contracts 完成。待 `/speckit.tasks` 產出 task list。main 已 merge + push（`f819d0c`）。

**Next**:
- [ ] `/speckit.tasks` → 產出 tasks.md
- [ ] 實作 Memory Store + Cron Scheduler
- [ ] browse_task (BrowserPipeline) E2E 測試 — code 已寫但未實測
- [ ] `lifespan()` 160+ 行，可拆分但不急
- [ ] per-route model override 持久化
- [ ] 影片支援（agent team tool + frame-by-frame，未來階段）

**User Notes**:
- Claude 模型在 Copilot CLI 會跑 agent loop 很慢，用 gpt-5-mini 測試秒回
- SDK `list_models()` 不列出所有 model，但直接用 model ID 字串可以跑
- tunnel 設定在 `~/.cloudflared/config.yaml`：`bot.webric.dev` → `localhost:2999`
- 圖片設計：buffer 存 ref，LLM 自主決定是否下載
- **browse_task（Agent Team 瀏覽器搜尋）已實作但未 E2E 測試**：`pipeline/samples/browser.py`（BrowserPipeline + BrowserSearchNode 用 Playwright headless Chromium）、`tools/builtin/browse_task.py`（AGENT_TEAM_TRIGGER）。測試路徑：chatbot 呼叫 browse_task tool → scheduler.enqueue → RunnerPool → BrowserPipeline → Playwright 搜 Google → push 結果回 chat。需驗證 Playwright 在 server 環境能正常啟動
- Memory Store + Cron Scheduler spec/plan 完成（003-memory-scheduler branch），含 6 項 research decisions、3 type schemas、2 contracts
- memo tool description 設計：不讓 LLM 自己決定存什麼，而是偵測到有價值資訊時主動詢問使用者是否記下。行為引導放在 tool description 而非 system prompt，這樣所有 chatbot 自動生效

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
