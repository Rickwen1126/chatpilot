## 2026-03-22 10:20 — v2 Implementation + CodeTour + Code Review 完成

**Goal**: 實作 v2 全部 42 tasks，建立架構 CodeTour，code review 修 bug

**Done**:
- `/speckit.implement` 完成：9 phases, 42 tasks, 32 source files, 2259 LOC
- CodeTour `.tours/01-architecture-chatpilot-v2.tour`：Sky Eye 7 stops，追蹤 chat + async task 兩條 data flow
- Code review 兩輪，修了 10+ issues（見下方 Decisions）
- 23 tests passing, ruff clean
- Commit `d13a6c5`

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

**State**: Branch `002-new-mvp`, commit `d13a6c5`, clean working tree. 23 tests, ruff clean.

**Next**:
- [ ] E2E 驗證：啟動 server + LINE webhook 測試（T019, T029 未做）
- [ ] 私聊 busy gate 行為可能需要 idle 後自動 re-trigger（已封但可能重新討論）
- [ ] `ContextMessageType.mention_busy` enum value 已無人使用，待清理
- [ ] `lifespan()` 160+ 行，可拆分但不急
- [ ] per-route model override 持久化（plan.md Open Questions）

**User Notes**:
- 查看下一步

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
