## 2026-03-24 20:47 — General Agent Pipeline + CronScheduler Config + Workspace + 盤點設計討論

**Goal**: 實作 plan（general-agent pipeline、cron config、pipeline result routing、workspace），接著討論倉庫盤點功能設計

**Done**:
- GeneralAgentPipeline — SDK session-based LLM pipeline (`pipeline/samples/general_agent.py`)
- CronSchedulerConfig — `available_tools` validation in routes.yaml
- Schedule.pipeline_name → tool_name — DB migration (ALTER COLUMN)
- Hub.receive_pipeline_result() — queue + idle drain infrastructure (Phase 2: via_chatbot ready)
- Reminder → enqueue general-agent (instead of direct hub.push)
- schedule_task_cron — validates tool_name against available_tools, dynamic description
- TaskInfo.reply_mode + TaskStore migration (input_data, reply_mode columns)
- SDK session working_directory — per-session workspace auto-created at `data/workspace/{session_id}/`
- ChatbotConfig.workdir for config override, system_message auto-injects `[工作目錄]`
- Fix E2E script CLI arg order (`--url` before subcommand)
- E2E checklist updated with new test scenarios (workspace, pipeline, schedule)
- All 21 E2E tests passing, 70 unit tests passing
- Commit `0d89686`

**Decisions**:
- Hub pipeline result queue 跟 context buffer 對稱設計：context buffer = 使用者閒聊(mention drain)；pipeline result queue = 系統結果(idle drain)
- Phase 1: reply_mode="direct" only；Phase 2: via_chatbot 需接 ChatbotManager callback
- Workspace 預設 `data/workspace/{session_id}/`，config 可覆蓋，chatbot + pipeline 一律適用
- 倉庫盤點不需要 Hub 收集模式 — 互動式對話，chatbot + 強 model + 對的工具就夠
- STT delay — 先做看圖片 + warehouse 新工具
- batch_image_analyze: ≤5 張 chatbot 自己看，>5 張走 agent team pipeline
- download_media 已回傳 `binaryResultsForLlm` → chatbot 本身就有視覺能力

**State**: Branch `main`, commit `0d89686`. Server running port 2999. Plan file at `.claude/plans/wondrous-percolating-quasar.md`.

**Next**:
- [ ] batch_image_analyze tool (agent team trigger → vision pipeline)
- [ ] warehouse_inventory_lock tool (倉庫 API)
- [ ] warehouse_inventory_write tool (倉庫 API)
- [ ] stt_transcribe tool (Whisper API, deferred)
- [ ] Phase 2: via_chatbot pipeline result routing (Hub callback → ChatbotManager)

**User Notes**:
- 盤點是互動對話不是 data pipeline — 每則訊息帶語義（「這兩張同一個」「代表照片，下一張是整體」）
- 不需要 timestamp 關聯語音↔照片 — chatbot 直接問就好
- shinyipaint bot 就夠，不需要專用盤點 bot（tool 多了再拆）
- 歸檔路徑: `/Users/rickwen/code/shinyipaint-proj-1/warehouse/`
- Plan doc: `docs/plans/2026-03-24-inventory-collect-via-line.md`（原始版，部分設計已被對話推翻）
