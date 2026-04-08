# Tasks: Observation Retrieval V1

- Created: 2026-04-07
- Last Updated: 2026-04-08
- Status: completed

**Input**: Design documents from `/docs/observation-retrieval-v1/`
**Prerequisites**: `spec.md`, `plan.md`

**Tests**: 本功能必須補齊 unit / integration / self-contained E2E，並維持既有 `uv run ruff check src/ tests/`、`uv run pytest tests/`、`bash tests/e2e/run_e2e.sh` 綠燈。

**Organization**: Tasks are grouped by user story to keep each increment independently testable.

## Phase 1: Setup

**Purpose**: 建立 feature task baseline 與實作入口盤點

- [x] T001 更新 feature task baseline 與索引在 docs/observation-retrieval-v1/tasks.md、docs/observation-retrieval-v1/spec.md、docs/observation-retrieval-v1/plan.md
- [x] T002 盤點目前 observer capture/query 入口與依賴點在 src/chatpilot/core/types.py、src/chatpilot/server/__init__.py、src/chatpilot/hub/hub.py、src/chatpilot/memory/store.py、src/chatpilot/tools/builtin/query_observations.py

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: 建立 retrieval v1 所需的共用 schema、store 與 observer batch contract

**⚠️ CRITICAL**: No user story work should begin until this phase is complete

- [x] T003 擴充 observation retrieval config 型別 in src/chatpilot/core/types.py 新增 `ObservationProfileRetrievalConfig` 並讓 `ObservationProfileConfig` 支援 `retrieval.description`、`retrieval.keywords`
- [x] T004 更新 config loading / validation 與 example settings in src/chatpilot/core/config.py、config/route_settings.example.yaml，讓 retrieval metadata 成為正式 config schema
- [x] T005 新增 `ObservationEntry` model 與 route-owned projection 型別 in src/chatpilot/memory/types.py
- [x] T006 新增 `observation_entries` table、CRUD 與 query helper in src/chatpilot/memory/store.py
- [x] T007 重構 observer batch callback contract，讓 observation lane 可把結構化 batch payload 與來源 metadata 傳給 worker / projection path in src/chatpilot/hub/hub.py、src/chatpilot/server/__init__.py
- [x] T008 [P] 補 foundational unit tests in tests/unit/test_observation_retrieval_config.py、tests/unit/test_memory_store_observation_entries.py

**Checkpoint**: retrieval config schema、`observation_entries` store、observer batch payload contract 已成立

---

## Phase 3: User Story 1 - Profile-driven Capture + Projection (Priority: P1) 🎯 MVP

**Goal**: observer worker 真正尊重 `observation_profile.instructions`，並把 batch 結果同時寫入 `memory_observations` 與 route-owned `observation_entries`

**Independent Test**: 模擬 `warehouse_ops` capture 後，worker prompt 內含 profile instructions/categories/output contract，DB 同時出現一筆 `memory_observations` 與對應的 `observation_entries`

### Tests for User Story 1

- [x] T009 [P] [US1] 新增 observer worker prompt contract 單元測試 in tests/unit/test_observer_prompt_contract.py
- [x] T010 [P] [US1] 新增 observation projection 單元測試 in tests/unit/test_observation_entries_projection.py

### Implementation for User Story 1

- [x] T011 [US1] 實作 capture worker prompt builder in src/chatpilot/observer/prompting.py，明確承接 base role、`profile.instructions`、categories、output contract、`subject` / `reported_by_*` 規則
- [x] T012 [US1] 在 src/chatpilot/server/__init__.py 以 prompt builder 取代目前寫死的 observer prompt，並讓 worker session 使用強約束 contract
- [x] T013 [US1] 實作 observer batch → `ObservationEntry` projection builder in src/chatpilot/observer/projection.py
- [x] T014 [US1] 在 src/chatpilot/server/__init__.py、src/chatpilot/memory/store.py 導入 `memory_observations` + `observation_entries` 的雙寫入路徑
- [x] T015 [US1] 在 src/chatpilot/hub/context_buffer.py、src/chatpilot/hub/hub.py 保留 `reported_by_user_id` / `reported_by_name` 所需的來源 metadata，避免由 LLM 補猜

**Checkpoint**: capture worker 已不只是摘要器，而是能穩定落結構化知識到兩張表的 worker

---

## Phase 4: User Story 2 - Query-aware Candidate Shortlist (Priority: P1)

**Goal**: consumer route 的自然語言 query 可以先拿到 top-k candidate source routes，而不是 group 全查

**Independent Test**: 給定同一 group 內多個不同 profile 的 source routes，自然語言 query 能回傳正確排序的 shortlist，且 shortlist 來自 query-time current group membership

### Tests for User Story 2

- [x] T016 [P] [US2] 新增 candidate scoring 單元測試 in tests/unit/test_list_observation_candidates.py
- [x] T017 [P] [US2] 新增 query-time group expansion 單元測試 in tests/unit/test_observation_candidate_selection.py

### Implementation for User Story 2

- [x] T018 [US2] 實作 `list_observation_candidates` tool in src/chatpilot/tools/builtin/list_observation_candidates.py
- [x] T019 [US2] 在 src/chatpilot/tools/builtin/list_observation_candidates.py 實作 heuristic top-k candidate scoring（category / keywords / description / route label）
- [x] T020 [US2] 在 src/chatpilot/server/__init__.py 註冊 `list_observation_candidates` 並注入目前 `observation_groups` / route labels / profile retrieval metadata
- [x] T021 [US2] 補 route-scoped observation access hint 到 chatbot prompt plumbing in src/chatpilot/server/__init__.py，讓 consumer route 知道應先 shortlist 再決定查哪些 members

**Checkpoint**: chatbot 可以先拿到 query-aware shortlist，不需要直接 group 全查

---

## Phase 5: User Story 3 - Per-Member Retrieval Stack (Priority: P1)

**Goal**: chatbot 先 shortlist，再逐一查 member routes，各 source 各自回傳 per-source results，最終 merge/synthesize 交給 LLM

**Independent Test**: consumer route 問自然語言問題時，tool stack 依序呼叫 `list_observation_candidates` 與 `query_observation_member`，並從正確 source route 拿回答案，不要求 cross-source hard merge

### Tests for User Story 3

- [x] T022 [P] [US3] 新增 per-member retrieval 單元測試 in tests/unit/test_query_observation_member.py
- [x] T023 [P] [US3] 新增 tool stack integration 測試 in tests/unit/test_observation_retrieval_flow.py

### Implementation for User Story 3

- [x] T024 [US3] 實作 `query_observation_member` tool in src/chatpilot/tools/builtin/query_observation_member.py
- [x] T025 [US3] 在 src/chatpilot/memory/store.py 新增 per-route observation entry query API，支援 days / limit / profile-aware ranking
- [x] T026 [US3] 在 src/chatpilot/server/__init__.py 註冊 `query_observation_member` 並把它接進 chatbot tool set
- [x] T027 [US3] 調整 src/chatpilot/tools/builtin/query_observations.py 與相關 prompt guidance，讓舊 `query_observations` 留作 compatibility path，而主查詢改走 shortlist + member query stack

**Checkpoint**: 自然語言 group knowledge 查詢已成立，不做 RAG 也能走完整 tool stack

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: 完整驗證、E2E、文件與回歸收尾

- [x] T028 [P] 新增 self-contained E2E scenario in tests/e2e/run_e2e.sh，驗證 `list_observation_candidates` → `query_observation_member` tool call stack 與 `observation_entries` side effect
- [x] T029 [P] 補 integration / regression fixtures in tests/unit/test_session_context.py、tests/unit/test_query_observations_group.py，確認舊 `query_observations` compatibility 不壞
- [x] T030 跑 `uv run ruff check src/ tests/` 並修正 lint issues
- [x] T031 跑 `uv run pytest tests/` 並修正 regression
- [x] T032 跑 `bash tests/e2e/run_e2e.sh` 並確認 observation retrieval v1 全鏈路正確
- [x] T033 [P] 更新 docs/todo/20260406.md、docs/observation-retrieval-v1/spec.md、docs/observation-retrieval-v1/plan.md 的實作狀態與 E2E checklist
- [ ] T034 依 milestone workflow 產生 codetour / review artifact 並 commit

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1**: No dependencies
- **Phase 2**: Depends on Phase 1
- **Phase 3**: Depends on Phase 2
- **Phase 4**: Depends on Phase 2 and uses the capture/projection primitives from Phase 3
- **Phase 5**: Depends on Phase 4
- **Phase 6**: Depends on desired user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational phase
- **User Story 2 (P1)**: Depends on Foundational phase and should follow once retrieval metadata / route-owned projection shape is stable
- **User Story 3 (P1)**: Depends on User Story 2 shortlist path existing

### Parallel Opportunities

- T008 can run in parallel with late foundational implementation once file targets are fixed
- T009 and T010 can run in parallel
- T016 and T017 can run in parallel
- T022 and T023 can run in parallel
- T028 and T029 can run in parallel after implementation settles

---

## Parallel Example: User Story 2

```bash
Task: "新增 candidate scoring 單元測試 in tests/unit/test_list_observation_candidates.py"
Task: "新增 query-time group expansion 單元測試 in tests/unit/test_observation_candidate_selection.py"
```

---

## Implementation Strategy

### MVP First

1. 完成 Phase 2 基礎 schema / store / observer batch contract
2. 完成 User Story 1，先把 capture worker 與 route-owned projection 做穩
3. 完成 User Story 2，先能 shortlist candidate members
4. 完成 User Story 3，補上 member query stack
5. 最後再做 E2E 與 compatibility 收尾

### Incremental Delivery

1. 先讓 observer 真正尊重 profile instructions 並穩定寫入 projection
2. 再讓 chatbot 先 shortlist，而不是直接 group 全查
3. 最後把 per-member query stack 接起來

## Notes

- V1 不做 vector RAG
- V1 不做 cross-source hard merge
- V1 不做 `rebuild_entries(route_id)` / `rebuild_entries(group)`
- `observation_entries` 是 route-owned projection，不是 current group/profile truth
- `query_observations` 保留 compatibility path，但主查詢路徑應轉向 shortlist + member query
