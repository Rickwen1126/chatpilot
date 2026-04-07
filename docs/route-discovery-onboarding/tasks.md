# Tasks: Route Discovery Onboarding

**Input**: Design documents from `/docs/route-discovery-onboarding/`
**Prerequisites**: `spec.md`, `plan.md`

**Tests**: 這輪需要 unit / integration / self-contained E2E，驗證 `follow/join` 不進一般 chatbot flow、runtime onboarding state 會被第一則 message 沿用、以及 `/cli/routes` 可見 pre-message discovered routes。

**Organization**: Tasks are grouped by user story to keep each increment independently testable.

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: 補齊 feature task baseline 與 active backlog 對齊

- [x] T001 更新 active backlog 與 route discovery onboarding 索引在 docs/todo/20260406.md、docs/route-discovery-onboarding/spec.md、docs/route-discovery-onboarding/plan.md

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: 建立 discovery onboarding 所需的共用 schema 與 runtime state

- [x] T002 新增 discovery config 型別與驗證在 src/chatpilot/core/types.py
- [x] T003 新增 GatewayConfig 的 discovery_profiles / discovery_rules 載入與 cross-ref 驗證在 src/chatpilot/core/config.py
- [x] T004 建立 route onboarding runtime state model 與 registry 在 src/chatpilot/routing/onboarding.py
- [x] T005 [P] 補 config / runtime state 單元測試在 tests/unit/test_config.py、tests/unit/test_route_onboarding.py

**Checkpoint**: config schema 與 route onboarding registry 已可獨立驗證

---

## Phase 3: User Story 1 - Pre-message route discovery (Priority: P1) 🎯 MVP

**Goal**: `follow/join` 事件可在第一則 message 前建立 canonical route，且 discovery event 不進一般 chatbot flow

**Independent Test**: 模擬 `follow/join` webhook 後，不產生 reply、不進 Hub 一般 message path，但 runtime onboarding state 與 route label 已建立

### Tests for User Story 1

- [x] T006 [P] [US1] 新增 LINE parser 的 follow/join 單元測試在 tests/unit/test_multi_line_adapter.py
- [x] T007 [P] [US1] 新增 webhook discovery path 單元測試在 tests/unit/test_multi_line_webhook.py

### Implementation for User Story 1

- [x] T008 [US1] 擴充 LINE parser 支援 follow/join discovery event 在 src/chatpilot/adapters/line/parser.py
- [x] T009 [US1] 擴充 LINE adapter 暴露 discovery parse path 與 label enrichment 所需平台能力在 src/chatpilot/adapters/line/adapter.py
- [x] T010 [US1] 在 webhook handler 分流 discovery event 並避免進一般 chatbot flow 在 src/chatpilot/server/webhook.py
- [x] T011 [US1] 實作 discovery 當下的 label enrichment 與 route label 寫入在 src/chatpilot/server/webhook.py

**Checkpoint**: follow/join 可以建立 discovered route 與 label，但尚未影響第一則 message routing

---

## Phase 4: User Story 2 - Discovery profile application (Priority: P1)

**Goal**: discovery 當下可依規則套用 route policy，第一則真正 message 直接沿用 onboarding state

**Independent Test**: 新 route discovery 後，第一則 `MessageEvent` 會命中 onboarding state，而不是回到 static binding/fallback

### Tests for User Story 2

- [x] T012 [P] [US2] 新增 discovery rule precedence 與 profile materialization 單元測試在 tests/unit/test_route_onboarding.py
- [x] T013 [P] [US2] 新增 router precedence 單元測試在 tests/unit/test_binding.py、tests/unit/test_route_onboarding.py
- [x] T014 [P] [US2] 新增 observer/runtime policy refresh 單元測試在 tests/unit/test_observer_reload.py

### Implementation for User Story 2

- [x] T015 [US2] 實作 discovery profile / rule matching 與 runtime onboarding materialization 在 src/chatpilot/routing/onboarding.py
- [x] T016 [US2] 讓 BindingRouter 優先解析 runtime onboarding state 在 src/chatpilot/routing/router.py
- [x] T017 [US2] 讓 server startup / reload 可重建並重新套用 onboarding state 與 observation_groups 在 src/chatpilot/server/__init__.py
- [x] T018 [US2] 讓 Hub route policy / capture registration 可接受 onboarding state 套用在 src/chatpilot/server/__init__.py、src/chatpilot/hub/hub.py

**Checkpoint**: discovery profile 能 materialize route policy，且第一則 message 直接命中 onboarding state

---

## Phase 5: User Story 3 - Admin visibility for discovered routes (Priority: P2)

**Goal**: pre-message discovered routes 能在 `/cli/routes` 可見，並能與既有 label/catalog flow 協作

**Independent Test**: follow/join 後，即使沒有 session，`/cli/routes` 也能列出新 route 與其 label / policy 摘要

### Tests for User Story 3

- [x] T019 [P] [US3] 新增 `/cli/routes` 讀取 onboarding state 的單元測試在 tests/unit/test_session_context.py、tests/unit/test_multi_line_webhook.py
- [x] T020 [P] [US3] 新增 `/cli/routes/sync` 與 discovered routes 並存的單元測試在 tests/unit/test_multi_line_webhook.py

### Implementation for User Story 3

- [x] T021 [US3] 擴充 `/cli/routes` 聚合 discovered routes 與 runtime onboarding metadata 在 src/chatpilot/server/webhook.py
- [x] T022 [US3] 擴充 `/cli/routes/sync` 可處理 discovered routes 與既有 session routes 在 src/chatpilot/server/webhook.py
- [x] T023 [US3] 更新範例 config 與文件說明 discovery_profiles / discovery_rules 在 `config/route_settings.example.yaml`、`config/route_bindings.example.yaml`、[spec.md](/Users/rickwen/code/chatpilot/docs/route-discovery-onboarding/spec.md)

**Checkpoint**: 管理者可在不送第一則 message 的前提下看到 discovered routes

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: 完整驗證、文件同步、回歸測試

- [x] T024 [P] 新增 self-contained discovery onboarding E2E 在 tests/e2e/run_e2e.sh 與對應 helper
- [x] T025 跑 `uv run ruff check src/ tests/`、`uv run pytest tests/`、`bash tests/e2e/run_e2e.sh` 並修正回歸
- [x] T026 [P] 更新 docs/todo/20260406.md 與 docs/route-discovery-onboarding/plan.md 的實作狀態
- [x] T027 產出本 milestone 的 codetour / review artifact 與 commit

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1**: No dependencies
- **Phase 2**: Depends on Phase 1
- **Phase 3**: Depends on Phase 2
- **Phase 4**: Depends on Phase 3
- **Phase 5**: Depends on Phase 4
- **Phase 6**: Depends on desired user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational phase
- **User Story 2 (P1)**: Depends on User Story 1 discovery path existing
- **User Story 3 (P2)**: Depends on User Story 2 runtime onboarding state existing

### Parallel Opportunities

- T005 can run in parallel with early schema work once file targets are fixed
- T006/T007 can run in parallel
- T012/T013/T014 can run in parallel
- T019/T020 can run in parallel
- T024/T026 can run in parallel after implementation settles

---

## Parallel Example: User Story 1

```bash
Task: "新增 LINE parser 的 follow/join 單元測試在 tests/unit/test_multi_line_adapter.py"
Task: "新增 webhook discovery path 單元測試在 tests/unit/test_multi_line_webhook.py"
```

---

## Implementation Strategy

### MVP First

1. 完成 Phase 2 基礎 schema / runtime registry
2. 完成 User Story 1 discovery path
3. 完成 User Story 2 onboarding materialization 與 routing precedence
4. 驗證第一則 message 不再落回 fallback

### Incremental Delivery

1. discovery event 可先被接住與建 label
2. 再套 profile 與 onboarding state
3. 最後補 admin visibility 與 E2E

---

## Notes

- `system/admin broadcast` 明確 defer，不在這輪 tasks 內
- v1 只做 `follow/join`、discovery profile/rule、runtime onboarding state、admin 可見性
- persisted onboarding state、`memberJoined`、進階 capabilities 留後續
