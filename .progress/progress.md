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
