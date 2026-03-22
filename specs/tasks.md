# Tasks: Agent Gateway MVP v2

**Input**: Design documents from `/specs/002-new-mvp/`
**Prerequisites**: plan.md, spec.md, data-model.md, contracts/, research.md, quickstart.md

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1–US6)
- All paths relative to repository root

---

## Phase 1: Setup

**Purpose**: v2 目錄結構與專案設定

- [x] T001 建立 v2 目錄結構：移除 v1 模組（dispatch/, processing/, queue/, server/session_gate.py），建立新 package 目錄（hub/, routing/, chatbot/, tools/, scheduler/, pipeline/, adapters/, sdk/）含 `__init__.py`，保留 core/, agents/, cli/, server/
- [x] T002 [P] 更新 pyproject.toml：新增 aiosqlite 依賴，更新 version 為 0.2.0
- [x] T003 [P] 建立 config/routes.yaml 範例（完整 v2 schema：match_weights, bindings, chatbots, agents, scheduler）與 .env.example

---

## Phase 2: Foundational（Blocking Prerequisites）

**Purpose**: 所有 User Story 共用的核心基礎設施

**⚠️ 所有 US 任務必須等此 Phase 完成才能開始**

- [x] T004 定義核心型別 in src/chatpilot/core/types.py：Message（新增 is_mention, user_name, timestamp）, Response, ChatRoute, ChatbotConfig, Binding, MatchWeights, AgentConfig, SchedulerConfig, TaskInfo, TaskStatus, ContextMessage, ContextMessageType, NodeOutput, ToolDefinition, AccessLevel（全部 Pydantic v2 models / enums）
- [x] T005 [P] 定義錯誤型別 in src/chatpilot/core/errors.py：GatewayError base + AdapterError, BindingError, HubError, SchedulerError, PipelineError, ToolFactoryError, QueueFullError
- [x] T006 [P] 實作 Config loader in src/chatpilot/core/config.py：parse routes.yaml → GatewayConfig（Pydantic model 含 match_weights, bindings, chatbots, agents, scheduler）, 支援 watchdog 熱重載 callback
- [x] T007 [P] 定義 ChannelAdapter Protocol in src/chatpilot/adapters/protocol.py：platform property, verify_request, parse_messages, send_reply, push_message（per contracts/adapter.md）
- [x] T008 [P] 實作 SDK session helper in src/chatpilot/sdk/session.py：create_session, resume_session, destroy_session, send_and_wait wrapper（含 TimeoutError/ProcessExitedError 處理，per research.md R-001）
- [x] T009 實作 ToolFactory in src/chatpilot/tools/factory.py + src/chatpilot/tools/registry.py：register, get_tools_for_chatbot, get_tools_for_pipeline（含 access level 過濾 + agent team 遞迴防護），is_agent_team_tool, list_tools（per contracts/tool-factory.md）

**Checkpoint**: 核心型別、config、adapter protocol、SDK wrapper、tool factory 就緒。可開始 US 實作。

---

## Phase 3: US1 — 透過聊天頻道與 Chatbot 即時對話（P1）🎯 MVP

**Goal**: 使用者從 LINE 發訊息 → binding 路由 → chatbot 即時回覆。含群組 mention filter + context buffer。

**Independent Test**: 從 LINE 群組發送一則 @bot 訊息，確認 chatbot 即時回覆。

### Implementation

- [x] T010 [P] [US1] 實作 mention filter in src/chatpilot/hub/mention_filter.py：is_mention(message) 判斷邏輯（群組：檢查 is_mention flag；私聊：always True）
- [x] T011 [P] [US1] 實作 ContextBuffer in src/chatpilot/hub/context_buffer.py：append, drain, format_context（結構化格式 per research.md R-008：[背景]/[busy 期間] 標記 + --- 分隔），flush_to_disk（JSON 寫入 data/context/{route_id}/）, sliding window 機制（context_window 設定）
- [x] T012 [P] [US1] 實作 Binding Router in src/chatpilot/routing/binding.py + src/chatpilot/routing/router.py：calculate_score（match_weights 計分）, resolve（找最高分 binding → ChatRoute）, 無匹配時回傳 None（per FR-009, FR-011）
- [x] T013 [US1] 定義 MessageHub Protocol in src/chatpilot/hub/protocol.py + 實作 InMemoryMessageHub in src/chatpilot/hub/hub.py：receive（prefix command 攔截 → mention filter → busy/idle 判斷 → 放行或攔截 + context buffer 操作）, send_reply, push, get_status/set_busy/set_idle（per contracts/message-hub.md 的完整 inbound 策略）。Hub 只做 gate + context，不知道 router / chatbot 存在。放行時呼叫 `on_proceed(message, context_prefix, adapter)` callback（由 app factory 注入，串接 router → chatbot）。Prefix command（`/model {name}`）攔截後呼叫 `on_command(command, args, message, adapter)` callback
- [x] T014 [P] [US1] 實作 ChatbotSession in src/chatpilot/chatbot/session.py：wrap SDK session，持有 model/system_message/tools config，send_message(text, context_prefix=None)（串接 context prefix + user message 後送 SDK send_and_wait），錯誤處理（friendly error response）。注意：model 切換不在 session 內部做（SDK session model 不可變），由 ChatbotManager 在 session 之上處理
- [x] T015 [US1] 實作 ChatbotManager in src/chatpilot/chatbot/manager.py：per-route session pool（get_or_create_session），依 ChatRoute.chatbot_name 查 ChatbotConfig，建立 ChatbotSession。switch_model(route_id, new_model)：destroy 當前 session → 用新 model create 新 session，永久生效（更新 runtime config）
- [x] T016 [P] [US1] 實作 LINE adapter in src/chatpilot/adapters/line/parser.py + src/chatpilot/adapters/line/adapter.py：verify_request（X-Line-Signature）, parse_messages（含 is_mention 偵測 + user_name 提取）, send_reply（Reply API + 截斷）, push_message（Push API）（基於 v1 重構，新增 push + is_mention）
- [x] T017 [US1] 實作 webhook handler in src/chatpilot/server/webhook.py：POST /webhook/{platform}（找 adapter → verify → parse → hub.receive）, GET /health，非阻塞處理（per contracts/webhook-api.md）
- [x] T018 [US1] 實作 FastAPI app factory in src/chatpilot/server/app.py：lifespan context manager，初始化所有元件（config loader, tool factory, binding router, message hub, chatbot manager, adapters），註冊 webhook routes，連接 hub → router → chatbot manager 的完整 inbound → process → outbound 流程
- [ ] T019 [US1] End-to-end 驗證：啟動 server + cloudflared tunnel，從 LINE 群組發送 @bot 訊息確認即時回覆。驗證：(1) 群組非 @bot 訊息不回應但存入 buffer (2) @bot 訊息帶 context prefix 回覆 (3) busy 時回覆「處理中」(4) 私聊直接回覆 (5) /model 切換生效

**Checkpoint**: US1 完成。Chatbot 即時對話可獨立運作。

---

## Phase 4: US2 — Assign 任務給 Agent Team 異步執行（P1）

**Goal**: 使用者透過 chatbot assign 任務 → scheduler queue → pipeline 異步執行 → push 結果回原對話。

**Independent Test**: Assign 一個任務，確認立即收到「任務已排定」通知，任務完成後收到 push 結果。

### Implementation

- [x] T020 [P] [US2] 定義 TaskScheduler Protocol in src/chatpilot/scheduler/protocol.py：enqueue, get_task, list_tasks, start, stop（per contracts/scheduler.md）
- [x] T021 [P] [US2] 實作 TaskStore in src/chatpilot/scheduler/store.py：SQLite WAL mode（data/tasks.db），save, get, list（per research.md R-005 的 schema：tasks table + indexes）
- [x] T022 [US2] 實作 InMemoryTaskScheduler in src/chatpilot/scheduler/scheduler.py：asyncio.Queue + enqueue（含 max_queue_size backpressure check）, start/stop lifecycle
- [x] T023 [US2] 實作 RunnerPool in src/chatpilot/scheduler/runner.py：asyncio.Semaphore(concurrent_runners)，從 queue 取 task → 執行 pipeline → 更新 task status → push 結果回 hub → 儲存到 store（per contracts/scheduler.md runner 行為）
- [x] T024 [P] [US2] 定義 PipelineNode Protocol in src/chatpilot/pipeline/node.py + 實作 PipelineExecutor in src/chatpilot/pipeline/executor.py：依序執行 node chain，自動注入 metadata（duration_ms, node_name），error 時中止 pipeline，max_iterations 安全閥（per contracts/pipeline.md）
- [x] T025 [P] [US2] 實作 Memory Tool in src/chatpilot/pipeline/memory.py：JSON file-based KV store（data/memory/{task_id}/），get/set/list_keys/delete（per research.md R-004）
- [x] T026 [US2] 實作 submit_task tool in src/chatpilot/tools/builtin/submit_task.py：建立 TaskInfo（uuid4），enqueue 到 scheduler，回傳「任務已排定，ID: {short_id}」。註冊為 chatbot_only access level, is_agent_team_tool=True
- [x] T027 [US2] 實作 sample echo pipeline in src/chatpilot/pipeline/samples/echo.py：單一 node，收到 input 直接回傳，作為 pipeline 框架驗證 + 開發範本
- [x] T028 [US2] 整合 scheduler 到 app factory：在 lifespan 中啟動 RunnerPool，註冊 submit_task tool 到 ToolFactory，chatbot config 的 agent team tool 名稱對應到 pipeline
- [x] T029 [US2] End-to-end 驗證：assign 任務（透過 chatbot 呼叫 agent team tool）→ 確認立即收到排定通知 → pipeline 執行完成 → push 結果回原對話。驗證：(1) chatbot 不被 task blocking (2) 連續 assign 多個任務可並行 (3) 任務失敗時 push 錯誤通知

**Checkpoint**: US1 + US2 完成。Chat + Task 雙層分離可獨立運作。

---

## Phase 5: US3 — 透過 CLI 直接與 Chatbot/Pipeline 互動（P2）

**Goal**: 開發者透過 CLI 直接與 chatbot 對話或觸發 pipeline，不需啟動 webhook server。

**Independent Test**: CLI 發送訊息確認 chatbot 回應。CLI 觸發 pipeline 確認結果輸出至 stdout。

### Implementation

- [x] T030 [P] [US3] 實作 CLI adapter in src/chatpilot/adapters/cli/__init__.py：stdin/stdout 互動，實作 ChannelAdapter Protocol（verify_request=True, parse=stdin, send_reply=stdout, push=stdout）
- [x] T031 [US3] 重寫 CLI main in src/chatpilot/cli/main.py：--chatbot {name} --message {text}（chatbot 模式）, --pipeline {name} --input {json}（pipeline 模式），共用 config/tool factory/chatbot manager/pipeline executor
- [x] T032 [US3] 驗證 CLI：chatbot 對話回應正確 + pipeline 同步執行結果輸出至 stdout

**Checkpoint**: US3 完成。開發者有本地測試路徑。

---

## Phase 6: US4 — Binding 路由將訊息導向正確 Chatbot（P3）

**Goal**: 多 chatbot 場景的完整 binding 路由：score 競爭、chatbot 切換指令、並行 session。

**Independent Test**: 設定不同 binding 對應不同 chatbot，驗證匹配正確 + 切換永久生效。

### Implementation

- [x] T033 [P] [US4] 實作 binding 切換指令：在 chatbot 的 /model 指令基礎上新增 /chatbot {name} 指令（ChatbotSession 或 tool），切換後覆蓋 binding 永久生效（需持久化到 config 或 override store）
- [x] T034 [US4] 驗證 multi-binding 路由：(1) group A → chatbot-x, group B → chatbot-y 並行 (2) 無匹配 → error log + 不回應 (3) platform-level + group-level → 高分勝出 (4) /chatbot 切換後永久生效

**Checkpoint**: US4 完成。Multi-chatbot 路由完整。

---

## Phase 7: US5 — 查看任務歷史（P3）

**Goal**: 使用者可在對話中查詢任務歷史（列表 + 特定任務結果）。

**Independent Test**: Assign 數個任務後，透過 chatbot 查詢歷史確認完整。

### Implementation

- [x] T035 [US5] 實作 task_history tool in src/chatpilot/tools/builtin/task_history.py：list_tasks（按狀態/時間列出摘要），get_task_detail（特定任務完整結果）。註冊為 chatbot_only access level。chatbot config 設 task_history: true 時自動加入
- [x] T036 [US5] 驗證任務歷史：(1) 查詢列出已完成 + 進行中任務 (2) 查詢特定 ID 回傳完整結果 (3) 無結果時回覆「目前沒有任務記錄」

**Checkpoint**: US5 完成。任務追蹤可用。

---

## Phase 8: US6 — 新增頻道 Adapter 不影響核心（P4）

**Goal**: 架構驗證 — 新增 mock adapter 時核心程式碼零修改。

**Independent Test**: 新增 mock adapter，確認只新增 adapter 檔案 + 註冊，核心零修改。

### Implementation

- [x] T037 [P] [US6] 實作 MockAdapter in src/chatpilot/adapters/mock/__init__.py：in-memory message buffer，實作 ChannelAdapter Protocol，verify=True, parse 從 JSON body, send_reply/push 存入 buffer 供測試讀取
- [x] T038 [US6] 驗證架構隔離：(1) 新增 mock adapter 時核心程式碼零修改 (2) 透過 POST /webhook/mock 測試完整流程 (3) SC-006 通過

**Checkpoint**: US6 完成。Ports & Adapters 架構驗證通過。

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: 跨 US 的品質改善

- [x] T039 [P] Config 熱重載完善：watchdog 監聽 routes.yaml 變更 → 重載 bindings/chatbots/scheduler config，不重啟 server（FR-032）
- [x] T040 [P] 完整 logging：統一 logging 格式（JSON structured），覆蓋訊息進出、binding 結果、task 狀態、pipeline 過程、push 結果（FR-036）
- [x] T041 邊界情況 hardening：(1) 特殊字元 / 超長文字 / 空白不崩潰 (2) Queue 滿回覆「系統忙碌」(3) Push 失敗 send & forget (4) 含迴圈 node 的 max_iterations 安全閥
- [x] T042 執行 ruff check + pytest 全量測試，確認全部通過

---

## Dependencies & Execution Order

### Phase Dependencies

```
Phase 1 (Setup) → Phase 2 (Foundational) → Phase 3+ (User Stories)
                                              ↓
                                     Phase 9 (Polish)
```

### User Story Dependencies

| Story | 依賴 | 說明 |
|-------|------|------|
| US1 (P1) | Phase 2 | 核心 MVP，無 US 間依賴 |
| US2 (P1) | Phase 2 + US1 | 需要 chatbot + hub 才能 assign task 和 push 結果 |
| US3 (P2) | Phase 2 + US1 | 共用 chatbot session；如需 pipeline 則也需 US2 |
| US4 (P3) | US1 | 擴展 US1 的 binding 路由 |
| US5 (P3) | US2 | 需要 task store 才有歷史可查 |
| US6 (P4) | US1 | 驗證 adapter 架構隔離 |

### Within Each User Story

1. Protocol / model 定義優先
2. 核心服務實作
3. 整合串接
4. End-to-end 驗證

### Parallel Opportunities

**Phase 2 內**：T005, T006, T007, T008 可全部並行（不同檔案）

**Phase 3 (US1) 內**：T010, T011, T012, T014, T016 可並行（不同模組）

**Phase 4 (US2) 內**：T020+T021, T024, T025 可並行

**跨 US**：US4, US5, US6 理論上可並行（各自不同模組），但建議 US1 → US2 → 其餘

---

## Parallel Example: Phase 3 (US1)

```text
# 第一波並行（無依賴）：
T010: mention_filter.py
T011: context_buffer.py
T012: binding.py + router.py
T014: chatbot/session.py
T016: LINE adapter

# 第二波（依賴第一波）：
T013: hub.py（依賴 T010, T011, T012）
T015: chatbot/manager.py（依賴 T014）

# 第三波（串接）：
T017: webhook.py
T018: app.py
T019: E2E 驗證
```

---

## Implementation Strategy

### MVP First（US1 Only）

1. Phase 1: Setup
2. Phase 2: Foundational
3. Phase 3: US1 — chatbot 即時對話
4. **STOP & VALIDATE**: LINE E2E 測試
5. 可 deploy/demo

### Core Product（US1 + US2）

1. Setup + Foundational
2. US1 → E2E 驗證
3. US2 → E2E 驗證
4. **STOP & VALIDATE**: Chat + Task 雙層分離完整運作
5. 這是真正的 MVP — chat 不只是聊天，還能 assign async task

### Full MVP（All US）

1. Setup + Foundational → US1 → US2（core path）
2. US3（開發工具）+ US4（multi-binding）+ US5（task history）
3. US6（架構驗證）
4. Polish
5. 全部 Success Criteria 通過

---

## Summary

| Phase | Tasks | 說明 |
|-------|-------|------|
| Phase 1: Setup | 3 | 目錄結構 + 設定 |
| Phase 2: Foundational | 6 | 核心型別 + config + protocols |
| Phase 3: US1 (P1) | 10 | Chatbot 即時對話 🎯 MVP |
| Phase 4: US2 (P1) | 10 | Async Task 執行 |
| Phase 5: US3 (P2) | 3 | CLI 工具 |
| Phase 6: US4 (P3) | 2 | Multi-binding 路由 |
| Phase 7: US5 (P3) | 2 | 任務歷史 |
| Phase 8: US6 (P4) | 2 | Mock adapter 架構驗證 |
| Phase 9: Polish | 4 | Logging + 邊界情況 |
| **Total** | **42** | |
