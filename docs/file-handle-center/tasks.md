# Tasks: FileHandleCenter

## Task Format

All tasks use the required checklist format:

`- [ ] [TaskID] [P?] [Story?] Description with file path`

## Phase 1: Setup

**Purpose**: 建立 file feature 的目錄、文件與測試骨架。

- [ ] T001 Create file feature package skeleton in `src/chatpilot/files/__init__.py`, `src/chatpilot/files/models.py`, `src/chatpilot/files/store.py`, `src/chatpilot/files/layout.py`, `src/chatpilot/files/policy.py`, `src/chatpilot/files/center.py`, and `src/chatpilot/files/ingress.py`
- [ ] T002 [P] Create file feature test skeletons in `tests/unit/test_file_models.py`, `tests/unit/test_file_handle_center.py`, `tests/integration/test_file_store.py`, `tests/integration/test_file_ingress.py`, and `tests/integration/test_file_vision.py`
- [ ] T003 [P] Align file feature docs cross-links in `docs/file-handle-center/spec.md` and `docs/file-handle-center/plan.md`

## Phase 2: Foundational

**Purpose**: 完成所有 user stories 共用的 core contracts、DB schema、storage layout 與中心服務骨架。

- [ ] T004 Define `SourceHandleInput`, `CanonicalFileHandle`, `SourceFetchResult`, and `MaterializedAsset` in `src/chatpilot/files/models.py`
- [ ] T005 Update adapter file contract in `src/chatpilot/adapters/protocol.py` to support source-handle translation and async source fetch
- [ ] T006 Implement `file_assets`, `file_relations`, and `file_notes` schema creation plus CRUD helpers in `src/chatpilot/files/store.py`
- [ ] T007 [P] Implement route-partition storage path generation and local asset layout helpers in `src/chatpilot/files/layout.py`
- [ ] T008 [P] Implement retention, scan status, and eager/lazy policy helpers in `src/chatpilot/files/policy.py`
- [ ] T009 Implement `FileHandleCenter` skeleton with `register`, `download_now`, `prefetch`, `get_asset`, and `ensure_local` in `src/chatpilot/files/center.py`
- [ ] T010 Wire `FileHandleCenter` and its store into app startup in `src/chatpilot/server/__init__.py`
- [ ] T011 [P] Add mock-based unit tests for models and center skeleton in `tests/unit/test_file_models.py` and `tests/unit/test_file_handle_center.py`
- [ ] T012 [P] Add integration tests for SQLite schema, CRUD, and storage layout in `tests/integration/test_file_store.py`

## Phase 3: User Story 1 — Route-level File Memory After Session Reset

**Goal**: 使用者在 session 重置後，仍可依 route-level file memory 找回昨天的圖片/文件脈絡，而不是只能重傳。

**Independent Test Criteria**: 建立 file record、note 與 route 關聯後，即使原始 session 不存在，系統仍可透過 route 查到前一天 file metadata / notes；原始 asset 過期後 metadata / notes 仍保留。

- [ ] T013 [US1] Implement route-scoped file query helpers and file-note persistence in `src/chatpilot/files/store.py`
- [ ] T014 [US1] Extend `FileHandleCenter` with route lookup helpers and note write/read helpers in `src/chatpilot/files/center.py`
- [ ] T015 [P] [US1] Add retention expiry behavior that removes local asset but preserves metadata / notes in `src/chatpilot/files/center.py` and `src/chatpilot/files/policy.py`
- [ ] T016 [P] [US1] Add integration tests for route-level lookup, note persistence, and post-expiry recall in `tests/integration/test_file_store.py` and `tests/unit/test_file_handle_center.py`

## Phase 4: User Story 2 — Governed Excel / Generated File Handling

**Goal**: 使用者請 bot 整理 Excel 或 agent/tool/pipeline 產出新檔時，檔案要被正式 register、建立 lineage，而不是亂丟 workpath。

**Independent Test Criteria**: 系統可將 generated file 納管為 `file_id`，建立與 source file / tool / pipeline 的 relation，並可透過 `ensure_local` 或 file lookup 安全地被下游流程再次使用。

- [ ] T017 [US2] Implement generated-file registration and relation write helpers in `src/chatpilot/files/center.py` and `src/chatpilot/files/store.py`
- [ ] T018 [US2] Add `generated_by_tool`, `generated_by_pipeline`, and `derived_from` relation helpers in `src/chatpilot/files/store.py`
- [ ] T019 [P] [US2] Add file-note support for summary / analysis / transcript / annotation in `src/chatpilot/files/store.py` and `src/chatpilot/files/models.py`
- [ ] T020 [P] [US2] Add integration tests for generated-file registration, relation lineage, and note persistence in `tests/integration/test_file_store.py`

## Phase 5: User Story 3 — Ingress Policy for Vision / STT / Document Workflows

**Goal**: 圖片、音檔、文件一進系統就先被 register，並依 policy 決定 eager/lazy/background，避免各流程自己重做 parser。

**Independent Test Criteria**: inbound image/audio/file 進入 hub 前會先經過 file ingress preprocessor；audio 可在 STT 前取得 canonical local asset；message flow 不再依賴 scattered parser 驅動後續下載。

- [ ] T021 [US3] Implement `InboundFilePreprocessor` / ingress service in `src/chatpilot/files/ingress.py`
- [ ] T022 [US3] Update `src/chatpilot/adapters/line/parser.py` and `src/chatpilot/adapters/line/adapter.py` to emit source-handle inputs for image/audio/file messages
- [ ] T023 [US3] Integrate ingress file preprocessing into `src/chatpilot/hub/hub.py` before STT / routing logic
- [ ] T024 [US3] Route audio prefetch / `ensure_local` into STT flow in `src/chatpilot/hub/hub.py` and `src/chatpilot/stt/transcriber.py`
- [ ] T025 [P] [US3] Add integration tests for LINE image/audio/file ingress and STT prefetch behavior in `tests/integration/test_file_ingress.py`

## Phase 6: User Story 4 — Unified Tool / Pipeline File Access

**Goal**: tool 與 pipeline 開發者透過同一套 center 存取 file，不再在每個工具重寫 adapter lookup、ref parse 與 local file hardcode。

**Independent Test Criteria**: `download_media`、`document_edit` 至少改為走 center API；pipeline/tool 可用 `file_id` / `ensure_local` 完成檔案存取，不再直接靠 platform ref parser 驅動核心流程。

- [ ] T026 [US4] Refactor `src/chatpilot/tools/builtin/download_media.py` to use `FileHandleCenter` records instead of direct adapter ref parsing as the primary path
- [ ] T027 [US4] Refactor `src/chatpilot/tools/builtin/document_edit.py` to use `FileHandleCenter.ensure_local(...)` and canonical file records
- [ ] T028 [US4] Wire `FileHandleCenter` into tool registration / dependency setup in `src/chatpilot/server/__init__.py`
- [ ] T029 [P] [US4] Add integration tests for `download_media` and `document_edit` using canonical file records in `tests/integration/test_file_tools.py`

## Phase 7: User Story 5 — Cross-Agent File Memory and Controlled Exposure

**Goal**: 檔案可被跨 agent / pipeline 有秩序地共享與回推，並以 relation + route scope 控制暴露，而不是各自 hardcode 路徑或 URL。

**Independent Test Criteria**: `show_image` 與 vision pipeline 會依 file origin / relation lineage / route scope 使用 canonical file records；vision model 可透過 local file attachment 真正讀圖。

- [ ] T030 [US5] Refactor `src/chatpilot/tools/builtin/show_image.py` to resolve file exposure through `FileHandleCenter` metadata and relation/route checks
- [ ] T031 [US5] Update `src/chatpilot/sdk/session.py` to support message `attachments` for local file delivery to the SDK
- [ ] T032 [US5] Rewrite `src/chatpilot/pipeline/samples/batch_vision.py` to use local file attachments instead of `download_media -> binaryResultsForLlm`
- [ ] T033 [P] [US5] Add vision POC / integration tests for local image attachment delivery in `tests/integration/test_file_vision.py`
- [ ] T034 [P] [US5] Add relation-driven exposure tests for `show_image` in `tests/integration/test_file_tools.py`

## Phase 8: Polish & Cross-Cutting

**Purpose**: 收斂剩餘 scattered logic、補齊 observability、完成 staged validation 與文件同步。

- [ ] T035 Remove or downgrade obsolete file/ref parsing paths in `src/chatpilot/tools/builtin/download_media.py`, `src/chatpilot/tools/builtin/show_image.py`, `src/chatpilot/tools/builtin/document_edit.py`, and `src/chatpilot/hub/hub.py`
- [ ] T036 [P] Add logging / debug traces for file register, policy decisions, local materialization, and cleanup in `src/chatpilot/files/center.py` and `src/chatpilot/files/ingress.py`
- [ ] T037 [P] Add cleanup job hooks and retention-class defaults in `src/chatpilot/files/policy.py`, `src/chatpilot/files/center.py`, and `src/chatpilot/server/__init__.py`
- [ ] T038 Add staged validation notes and E2E checklist updates in `docs/file-handle-center/spec.md`, `docs/file-handle-center/plan.md`, and `docs/todo/20260331.md`

## Dependencies

- Phase 1 → Phase 2
- Phase 2 must complete before all user stories
- US1 depends on Phase 2 only
- US2 depends on Phase 2 only
- US3 depends on Phase 2 and should complete before US4 / US5
- US4 depends on US3
- US5 depends on US2, US3, and US4
- Polish depends on all targeted story phases being integrated

## Suggested Delivery Order

1. Phase 1 + Phase 2
2. US3
3. US1
4. US2
5. US4
6. US5
7. Phase 8

## Parallel Opportunities

### Phase 2

- T007 and T008 can run in parallel after T004-T006
- T011 and T012 can run in parallel after T004-T010

### US1

- T015 and T016 can run in parallel after T013-T014

### US2

- T019 and T020 can run in parallel after T017-T018

### US3

- T025 can start once T021-T024 interface shape is stable

### US4

- T029 can run after T026-T028 are merged

### US5

- T033 and T034 can run in parallel after T030-T032

## Implementation Strategy

### MVP First

MVP scope:

- Phase 1
- Phase 2
- US3
- US1

這個範圍就足以建立：

- 中心本體
- DB/index
- hub ingress
- route-level file recall 基礎

### Staged Validation

- 先用 mock / unit / integration 證明 center 本身正確
- 再逐段串到 hub / adapter / STT / vision / tools
- 如果某段整合受前置進度阻塞，可先 skip，但要保留明確測試入口與待辦
- 進入需要 localhost:2999 測試 server / E2E 的階段前，先停止現有本機 chatpilot 服務，避免 port / tunnel / webhook 干擾
