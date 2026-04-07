# Tasks: Observer VNext

**Input**: Design documents from [docs/observer-vnext](/Users/rickwen/code/chatpilot/docs/observer-vnext)
**Prerequisites**: [spec.md](/Users/rickwen/code/chatpilot/docs/observer-vnext/spec.md), [plan.md](/Users/rickwen/code/chatpilot/docs/observer-vnext/plan.md)

**Tests**: 本功能必須補齊 unit / self-contained E2E，並維持既有 `ruff` / `pytest` / `bash tests/e2e/run_e2e.sh` 綠燈。

**Organization**: Tasks are grouped by user story to enable independent implementation and testing.

## Phase 1: Setup

**Purpose**: 建立 observer vNext 文件與執行基線

- [x] T001 更新 observer vNext 實作進度與執行順序到 docs/observer-vnext/tasks.md
- [x] T002 盤點現有 observer 實作入口與依賴點於 src/chatpilot/core/types.py、src/chatpilot/server/__init__.py、src/chatpilot/hub/hub.py、src/chatpilot/tools/builtin/query_observations.py

---

## Phase 2: Foundational

**Purpose**: 先建立新 schema 與 runtime 輔助結構，阻擋舊 observer config 繼續存在

**⚠️ CRITICAL**: No user story work should begin until this phase is complete

- [x] T003 更新 observer config schema in [src/chatpilot/core/types.py](/Users/rickwen/code/chatpilot/src/chatpilot/core/types.py) 新增 `RouteGroupConfig`、`ObservationProfileConfig`、`ObservationCaptureConfig`、`ObservationConfig`、`reply_policy`、`processing_policy`
- [x] T004 更新 gateway config loading in [src/chatpilot/core/config.py](/Users/rickwen/code/chatpilot/src/chatpilot/core/config.py) 支援 `route_groups` 與 `observation_profiles`
- [x] T005 [P] 補 cross-field validation in [src/chatpilot/core/types.py](/Users/rickwen/code/chatpilot/src/chatpilot/core/types.py) 限制只接受 `reply=never + processing=none` 與 `reply=addressed + processing=interactive`
- [x] T006 [P] 移除舊 observer config 欄位與 fallback 依賴 in [src/chatpilot/core/types.py](/Users/rickwen/code/chatpilot/src/chatpilot/core/types.py) 與 [src/chatpilot/server/__init__.py](/Users/rickwen/code/chatpilot/src/chatpilot/server/__init__.py)
- [x] T007 [P] 補 schema / config unit tests in [tests/unit/test_config.py](/Users/rickwen/code/chatpilot/tests/unit/test_config.py) 與新檔 [tests/unit/test_observer_vnext_config.py](/Users/rickwen/code/chatpilot/tests/unit/test_observer_vnext_config.py)

**Checkpoint**: 新 observer schema 成立，舊 observer config 會 fail fast

---

## Phase 3: User Story 1 - 靜默觀察來源 (Priority: P1) 🎯 MVP

**Goal**: 某些 route 可以不回話、不建立互動 chatbot session，但持續 capture 背景知識到 route-local observation storage

**Independent Test**: `reply=never + processing=none + capture` 的 route 不回話、不建互動 session，但 observation row 會寫入 DB

### Implementation for User Story 1

- [x] T008 [US1] 重寫 observer registration/runtime membership in [src/chatpilot/server/__init__.py](/Users/rickwen/code/chatpilot/src/chatpilot/server/__init__.py) 由 `binding.observation` 推導 source/consumer routes 與 route groups
- [x] T009 [US1] 在 [src/chatpilot/hub/hub.py](/Users/rickwen/code/chatpilot/src/chatpilot/hub/hub.py) 導入 `reply_policy` / `processing_policy` 的 canonical inbound 判定與 fan-out intent 邏輯
- [x] T010 [US1] 在 [src/chatpilot/hub/hub.py](/Users/rickwen/code/chatpilot/src/chatpilot/hub/hub.py) 建立 observation lane 專用 buffer / capture queue，避免共用現有 `ContextBuffer`
- [x] T011 [US1] 調整 observer batch summarize worker path in [src/chatpilot/server/__init__.py](/Users/rickwen/code/chatpilot/src/chatpilot/server/__init__.py) 明確走獨立 observation worker session
- [x] T012 [P] [US1] 更新 observer silence/runtime unit tests in [tests/unit/test_observer_silence.py](/Users/rickwen/code/chatpilot/tests/unit/test_observer_silence.py) 驗證 `reply=never + processing=none`
- [x] T013 [P] [US1] 新增 Hub fan-out / buffer boundary tests in [tests/unit/test_observer_vnext_hub.py](/Users/rickwen/code/chatpilot/tests/unit/test_observer_vnext_hub.py)

**Checkpoint**: 靜默觀察來源可以獨立成立，且不依賴互動 chatbot session

---

## Phase 4: User Story 2 - Addressed 互動 + 背景整理 (Priority: P1)

**Goal**: 同一條 route 可在 addressed 時回話，並同時 capture 背景知識，但 reply lane 與 observation lane 分離

**Independent Test**: `reply=addressed + processing=interactive + capture` 的 route 在 addressed 時可回話，非 addressed 時不回話，但 capture 仍能寫 observation，且 reply/summarize 走不同 buffer 與 session path

### Implementation for User Story 2

- [x] T014 [US2] 在 [src/chatpilot/hub/hub.py](/Users/rickwen/code/chatpilot/src/chatpilot/hub/hub.py) 明確區分 reply intent 與 observation intent 的 fan-out semantics
- [x] T015 [US2] 在 [src/chatpilot/hub/hub.py](/Users/rickwen/code/chatpilot/src/chatpilot/hub/hub.py) 保持 addressed 判定只影響 reply intent，不影響 observation capture
- [x] T016 [US2] 在 [src/chatpilot/server/__init__.py](/Users/rickwen/code/chatpilot/src/chatpilot/server/__init__.py) 與 session plumbing 中補明確 log，證明 reply path 與 observation worker path 是不同 session
- [x] T017 [P] [US2] 更新 unit tests in [tests/unit/test_observer_silence.py](/Users/rickwen/code/chatpilot/tests/unit/test_observer_silence.py) 與 [tests/unit/test_observer_vnext_hub.py](/Users/rickwen/code/chatpilot/tests/unit/test_observer_vnext_hub.py) 驗證 addressed + capture

**Checkpoint**: 同一路 route 的互動回話與背景整理能並行且不互相污染

---

## Phase 5: User Story 3 - Group-based 知識消費 (Priority: P1)

**Goal**: consumer route 能用 `group` 查詢共享背景知識，不再依賴 source label / chatbot name

**Independent Test**: `query_observations(group=...)` 可正確展開 source routes；consumer route 能查到，非 consumer route 查不到

### Implementation for User Story 3

- [x] T018 [US3] 重寫 query tool API in [src/chatpilot/tools/builtin/query_observations.py](/Users/rickwen/code/chatpilot/src/chatpilot/tools/builtin/query_observations.py) 以 `group` 為 canonical input
- [x] T019 [US3] 更新 observer source/query runtime state in [src/chatpilot/server/__init__.py](/Users/rickwen/code/chatpilot/src/chatpilot/server/__init__.py) 改為 group-based membership view
- [x] T020 [US3] 移除 source label / chatbot-name-derived source identity 依賴 in [src/chatpilot/tools/builtin/query_observations.py](/Users/rickwen/code/chatpilot/src/chatpilot/tools/builtin/query_observations.py) 與 [src/chatpilot/server/__init__.py](/Users/rickwen/code/chatpilot/src/chatpilot/server/__init__.py)
- [x] T021 [P] [US3] 更新 query_observations 相關 tests in [tests/unit/test_session_context.py](/Users/rickwen/code/chatpilot/tests/unit/test_session_context.py) 與新增 [tests/unit/test_query_observations_group.py](/Users/rickwen/code/chatpilot/tests/unit/test_query_observations_group.py)

**Checkpoint**: observer query 不再依賴 source label，group-based consume 成立

---

## Phase 6: User Story 4 - Repo Config Migration (Priority: P2)

**Goal**: repo 內正式 config 全面切到 observer vNext schema，沒有 active 舊 observer config

**Independent Test**: `config/route_settings.yaml`、`config/route_bindings.yaml`、`config/route_settings.example.yaml`、`config/route_bindings.example.yaml` 都可 parse，且不再包含舊 observer config 欄位

### Implementation for User Story 4

- [x] T022 [US4] 更新 production-like config in [route_settings.yaml](/Users/rickwen/code/chatpilot/config/route_settings.yaml) 與 [route_bindings.yaml](/Users/rickwen/code/chatpilot/config/route_bindings.yaml)，改用 `route_groups`、`observation_profiles`、`binding.reply_policy`、`binding.processing_policy`、`binding.observation`
- [x] T023 [P] [US4] 更新 example config in [route_settings.example.yaml](/Users/rickwen/code/chatpilot/config/route_settings.example.yaml) 與 [route_bindings.example.yaml](/Users/rickwen/code/chatpilot/config/route_bindings.example.yaml)，以及相關文件範例 in [README.md](/Users/rickwen/code/chatpilot/README.md)
- [x] T024 [US4] 更新 observer reload / config tests in [tests/unit/test_observer_reload.py](/Users/rickwen/code/chatpilot/tests/unit/test_observer_reload.py) 與 [tests/unit/test_config.py](/Users/rickwen/code/chatpilot/tests/unit/test_config.py)

**Checkpoint**: repo 不再以舊 observer config 作為正式做法

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: 完成驗證、E2E 與文件收尾

- [x] T025 [P] 補 self-contained E2E scenarios in [tests/e2e/run_e2e.sh](/Users/rickwen/code/chatpilot/tests/e2e/run_e2e.sh) 與相關 fixtures，覆蓋 `never/none + capture`、`addressed/interactive + capture`、`group query`
- [x] T026 [P] 跑 `uv run ruff check src/ tests/` 並修正 lint issues
- [x] T027 跑 `uv run pytest tests/` 並修正 regression
- [x] T028 跑 `bash tests/e2e/run_e2e.sh` 並確認 observer vNext 全鏈路正確
- [x] T029 依 milestone workflow 產生 codetour 與 review notes，更新 [docs/todo/20260403.md](/Users/rickwen/code/chatpilot/docs/todo/20260403.md) 或新當日 todo

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies
- **Foundational (Phase 2)**: Blocks all user stories
- **US1 (Phase 3)**: Depends on Foundational
- **US2 (Phase 4)**: Depends on US1 fan-out / worker boundary groundwork
- **US3 (Phase 5)**: Depends on Foundational; can overlap late US2 once membership/runtime shape is stable
- **US4 (Phase 6)**: Depends on Foundational and should land after runtime shape is stable
- **Polish (Phase 7)**: Depends on desired user stories being complete

### Parallel Opportunities

- T005 and T007 can run in parallel after schema shape is known
- T012 and T013 can run in parallel within US1
- T017 and T021 can run in parallel with their corresponding implementation tasks once APIs settle
- T023 can run in parallel with T022 once config shape is finalized
- T025 and T026 can run in parallel after implementation is complete

## Implementation Strategy

### MVP First

1. Finish Phase 2
2. Finish Phase 3
3. Validate `reply=never + processing=none + capture`
4. Then add addressed + capture
5. Then cut query API to `group`

### Incremental Delivery

1. Schema first, fail fast on old config
2. Silent observer source behavior stable
3. Addressed + capture behavior stable
4. Group-based query stable
5. Repo config migration and E2E hardening

## Notes

- 這輪不實作 `shadow`
- `route_group` 是一級配置，但不要把它寫死成永遠只有 `description`
- `reply_policy` 與 `processing_policy` 是合法組合矩陣，不是自由排列組合
