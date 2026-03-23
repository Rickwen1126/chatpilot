# Tasks: Memory Store + Cron Scheduler

**Input**: Design documents from `specs/003-memory-scheduler/`
**Prerequisites**: plan.md, spec.md, data-model.md, contracts/, research.md

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1–US4)
- All paths relative to repository root

---

## Phase 1: Setup

**Purpose**: 建立 memory/ 和 cron/ package 結構

- [x] T001 建立 memory package 結構：src/chatpilot/memory/__init__.py, protocol.py, store.py, types.py
- [x] T002 [P] 建立 cron package 結構：src/chatpilot/cron/__init__.py, scheduler.py, parser.py

---

## Phase 2: Foundational（Blocking Prerequisites）

**Purpose**: Memory Store Protocol + SQLite 實作 + Cron 解析器

**⚠️ 所有 US 任務必須等此 Phase 完成才能開始**

- [x] T000 定義 Memory Store types in src/chatpilot/memory/types.py：Memo, CustomPrompt, Reminder, Schedule（Pydantic v2 models），MemoryStatus enum（pending/running/completed/failed）。所有欄位 MUST 有 default 值
- [x] T000 [P] 定義 MemoryStore Protocol in src/chatpilot/memory/protocol.py：save, get, list, delete, update, query_due_before（per contracts/memory-store.md）
- [x] T000 實作 SqliteMemoryStore in src/chatpilot/memory/store.py：共用 data/chatpilot.db，4 張 table（memory_memos, memory_custom_prompts, memory_reminders, memory_schedules），WAL mode，initialize() 建 table + index
- [x] T000 [P] 實作 cron 表達式解析器 in src/chatpilot/cron/parser.py：parse_cron(expr) → 計算 next_run_at。支援 daily HH:MM、weekly DAY HH:MM、interval Nm/Nh 三種格式
- [x] T000 [P] 單元測試 in tests/unit/test_memory_store.py：CRUD 操作、type 驗證、query_due_before
- [x] T000 [P] 單元測試 in tests/unit/test_cron_parser.py：三種 cron 格式解析 + next_run_at 計算

**Checkpoint**: Memory Store CRUD + Cron Parser 就緒。可開始 US 實作。

---

## Phase 3: US1 — 記住事情（Memo） + 使用習慣（Custom Prompt）

**Goal**: 使用者透過 chatbot 存取 memo 和偏好。custom_prompt 更新後 session 自動重建。

**Independent Test**: 透過 CLI 存 memo → 查詢 → 刪除。存 custom_prompt → 驗證 session 重建。

### Implementation

- [x] T009 [P] [US1] 實作 save_memo tool in src/chatpilot/tools/builtin/save_memo.py：handler 遵守 ToolInvocation → ToolResult，自動帶 route_id。tool description 引導 LLM 主動詢問使用者是否記錄
- [x] T010 [P] [US1] 實作 list_memos tool in src/chatpilot/tools/builtin/list_memos.py：列出該 route 所有 memo
- [x] T011 [P] [US1] 實作 delete_memo tool in src/chatpilot/tools/builtin/delete_memo.py：刪除指定 memo
- [x] T012 [P] [US1] 實作 save_custom_prompt tool in src/chatpilot/tools/builtin/save_custom_prompt.py：儲存偏好 + 標記 session needs_rebuild。tool description 引導 LLM 偵測偏好時主動詢問
- [x] T013 [P] [US1] 實作 list_custom_prompts tool in src/chatpilot/tools/builtin/list_custom_prompts.py
- [x] T014 [P] [US1] 實作 delete_custom_prompt tool in src/chatpilot/tools/builtin/delete_custom_prompt.py：刪除偏好 + 標記 session needs_rebuild
- [x] T015 [US1] ChatbotSession 加 needs_rebuild 屬性 in src/chatpilot/chatbot/session.py：複用 broken pattern
- [x] T016 [US1] ChatbotManager 加 memory_store 依賴 + needs_rebuild 檢查 in src/chatpilot/chatbot/manager.py：constructor 加 memory_store 參數，get_or_create_session 檢查 needs_rebuild → destroy → 從 memory_store 讀該 route 的 custom_prompts → 合併到 system_message（格式：base + `[使用者偏好]` + list）→ create new session。log 明確標記「rebuild reason: custom_prompt updated」
- [x] T017 [US1] 整合到 app factory in src/chatpilot/server/__init__.py：初始化 MemoryStore，註冊 memo + custom_prompt tools，將 memory_store 傳入 ChatbotManager
- [x] T018 [US1] CLI E2E 驗證：chatpilot-cli chat "記住：明天開會" → chatpilot-cli chat "我記了什麼？" → 確認 memo 存取正常

**Checkpoint**: US1 完成。Memo + Custom Prompt 可獨立運作。

---

## Phase 4: US2 — 設定提醒（Reminder）

**Goal**: 使用者設定 reminder，CronScheduler 到期 push 通知。

**Independent Test**: 設定 1 分鐘後 reminder → 等待 → 確認收到 push。

### Implementation

- [x] T019 [P] [US2] 實作 add_reminder tool in src/chatpilot/tools/builtin/add_reminder.py：LLM 提供 text + due_at，存入 Memory Store（type=reminder, status=pending）
- [x] T020 [US2] 實作 CronScheduler in src/chatpilot/cron/scheduler.py：tick loop（asyncio, 60s interval），掃描 query_due_before("reminder", now)，到期 → status=running → hub.push → status=completed/failed + last_error。掃 status=failed → warning log
- [x] T021 [US2] 整合 CronScheduler 到 app factory in src/chatpilot/server/__init__.py：lifespan 啟動 CronScheduler（傳入 memory_store + hub），shutdown 時 stop
- [x] T022 [US2] 註冊 add_reminder tool 到 ToolFactory in src/chatpilot/server/__init__.py
- [x] T023 [P] [US2] 單元測試 in tests/unit/test_cron_scheduler.py：mock memory_store + mock hub，驗證 tick → 掃到 reminder → push → 更新 status
- [x] T024 [US2] CLI E2E 驗證：chatpilot-cli chat "1 分鐘後提醒我測試" → 等 60 秒 → 確認 push 通知

**Checkpoint**: US2 完成。Reminder + CronScheduler 可獨立運作。

---

## Phase 5: US3 — 定期排程任務（Scheduled Task）

**Goal**: 使用者設定 cron 排程，到期觸發 pipeline 並 push 結果。

**Independent Test**: 設定 interval 2m 排程 → 等 2 分鐘 → 確認 pipeline 執行 + push 結果。

### Implementation

- [x] T025 [P] [US3] 實作 schedule_task_cron tool in src/chatpilot/tools/builtin/schedule_task_cron.py：LLM 提供 cron_expr + pipeline_name + input_data，用 cron parser 算 next_run_at，存入 Memory Store（type=schedule, status=pending）
- [x] T026 [US3] CronScheduler 加 schedule handler in src/chatpilot/cron/scheduler.py：掃描 query_due_before("schedule", now)，到期 → status=running → task_scheduler.enqueue(TaskInfo) → 成功則算 next_run_at + reset pending → 失敗則 status=failed
- [x] T027 [US3] CLI E2E 驗證：chatpilot-cli chat "每 2 分鐘搜尋台股" → 等 2 分鐘 → 確認 pipeline 執行 + push 結果

**Checkpoint**: US3 完成。Schedule + Pipeline 觸發可運作。

---

## Phase 6: US4 — 查看和管理排程

**Goal**: 使用者可列出、取消 reminder 和 schedule。

**Independent Test**: 設定 reminder + schedule → list → cancel → 確認已取消。

### Implementation

- [x] T028 [P] [US4] 實作 list_schedules tool in src/chatpilot/tools/builtin/list_schedules.py：列出該 route 所有 reminder（pending）+ schedule（pending），合併顯示
- [x] T029 [P] [US4] 實作 cancel_schedule tool in src/chatpilot/tools/builtin/cancel_schedule.py：刪除指定 reminder 或 schedule
- [x] T030 [US4] CLI E2E 驗證：設定 reminder + schedule → chatpilot-cli chat "我有哪些排程？" → chatpilot-cli chat "取消第 1 個" → 確認已刪除

**Checkpoint**: US4 完成。排程管理可用。

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: config 更新、logging、edge case

- [x] T031 [P] 更新 config/routes.yaml：所有 chatbot 的 tools 列表加入 memo + custom_prompt + reminder + schedule 相關 tool
- [x] T032 [P] 更新 config/routes.example.yaml：同上
- [x] T033 [P] 完整 logging：Memory Store CRUD 操作 + CronScheduler tick/dispatch/success/failure 統一 log 格式
- [x] T034 邊界情況 hardening：(1) 空 memo 不存 (2) 過去的 due_at 立即觸發 (3) cron_expr 格式錯誤回友善錯誤 (4) route_id 推導失敗的處理
- [x] T035 執行 ruff check + pytest 全量測試，確認全部通過

---

## Dependencies & Execution Order

### Phase Dependencies

```
Phase 1 (Setup) → Phase 2 (Foundational) → Phase 3+ (User Stories)
                                              ↓
                                     Phase 7 (Polish)
```

### User Story Dependencies

| Story | 依賴 | 說明 |
|-------|------|------|
| US1 (Memo + Custom Prompt) | Phase 2 | 核心 MVP，無 US 間依賴 |
| US2 (Reminder) | Phase 2 + US1 部分 | 需要 Memory Store + CronScheduler |
| US3 (Schedule) | US2 | 需要 CronScheduler（US2 建立） |
| US4 (List/Cancel) | US2 | 需要有 reminder/schedule 可管理 |

### Parallel Opportunities

**Phase 2 內**：T004, T006, T007, T008 可全部並行

**Phase 3 (US1) 內**：T009–T014 可全部並行（各自獨立 tool 檔案）

**Phase 4 (US2) 內**：T019, T023 可並行

---

## Implementation Strategy

### MVP First（US1 Only）

1. Phase 1: Setup
2. Phase 2: Foundational
3. Phase 3: US1 — Memo + Custom Prompt
4. **STOP & VALIDATE**: CLI E2E 測試
5. 可 demo

### Core Product（US1 + US2）

1. Setup + Foundational
2. US1 → E2E 驗證
3. US2 → E2E 驗證（Reminder + CronScheduler）
4. **STOP & VALIDATE**: 設定 reminder → 等到期 → 確認 push

### Full Feature（All US）

1. Setup + Foundational → US1 → US2（core path）
2. US3（Schedule） + US4（管理）
3. Polish
4. 全部 Success Criteria 通過

---

## Summary

| Phase | Tasks | 說明 |
|-------|-------|------|
| Phase 1: Setup | 2 | Package 結構 |
| Phase 2: Foundational | 6 | Protocol + SQLite + Cron Parser + 測試 |
| Phase 3: US1 | 10 | Memo + Custom Prompt + Session Rebuild |
| Phase 4: US2 | 6 | Reminder + CronScheduler |
| Phase 5: US3 | 3 | Schedule + Pipeline 觸發 |
| Phase 6: US4 | 3 | 排程管理（list/cancel） |
| Phase 7: Polish | 5 | Config + Logging + Hardening |
| **Total** | **35** | |
