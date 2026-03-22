# Tasks: 通用 Agent Gateway MVP

**Input**: Design documents from `/specs/001-agent-gateway-mvp/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅, quickstart.md ✅

**Tests**: Unit, integration, and contract tests included in Phase 7.

**Organization**: Tasks grouped by user story (US1→US4) to enable independent implementation and validation of each story.

**Stack**: Python 3.11+ / FastAPI / uvicorn / uv / github-copilot-sdk / Pydantic v2

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1–US4)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Python project initialization — uv + pyproject.toml + directory skeleton

- [X] T001 Initialize uv project — run `uv init` and configure `pyproject.toml` with project name `chatpilot`, Python `>=3.11`, `src/chatpilot/` package layout, and scripts (`dev`, `start`, `cli`)
- [X] T002 [P] Add production dependencies to `pyproject.toml`: `github-copilot-sdk`, `line-bot-sdk`, `fastapi`, `uvicorn[standard]`, `pydantic>=2`, `watchdog`, `pyyaml`, `python-dotenv`
- [X] T003 [P] Add dev dependencies to `pyproject.toml` dev group: `pytest`, `pytest-asyncio`, `httpx`, `ruff`
- [X] T004 [P] Create directory tree per `plan.md`: `src/chatpilot/{core,channels/line,dispatch,agents/general,sdk,queue,server,cli}`, `tests/{unit,integration,contract}`, `config/`; add `__init__.py` to all Python packages
- [X] T005 [P] Create `.env.example` with all required variables: `LINE_CHANNEL_SECRET`, `LINE_CHANNEL_ACCESS_TOKEN`, `GITHUB_TOKEN`, `PORT` (default 3000), `REPLY_TIMEOUT_MS` (default 20000), `PENDING_QUEUE_TTL_MS` (default 1800000), `PUSH_API_ENABLED` (default false)
- [X] T006 [P] Create `config/routes.example.yaml` with annotated sample routing configuration per data-model.md (group with keyword + fallback, private chat rule)
- [X] T007 Run `uv sync` to generate `uv.lock` and verify all dependencies install successfully

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core types, Protocols, and SDK wrapper that ALL user stories depend on

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T008 Implement core types in `src/chatpilot/core/types.py` — Pydantic models from `contracts/types.py`: `Platform`, `Message`（加 Pydantic validator：`text` 不得為空字串、`platform` 不得為空字串）, `LinePlatformContext`, `Response`（`text` 不得為空字串）, `Attachment`, `RouteMap`, `RouteRule`, `KeywordMapping`, `PendingMessage`, `DispatchResult` union type (`KeywordMatch | FallbackMatch | Ignored`；`Ignored` 含 `reason: str` 欄位，預設 `"no_route"`)
- [X] T009 [P] Implement custom exceptions in `src/chatpilot/core/errors.py` — `AgentError`, `RouteError`, `AdapterError`, `TimeoutError` (all extend `Exception` with optional `cause` and string `code`)
- [X] T010 [P] Define ChannelAdapter Protocol in `src/chatpilot/channels/adapter.py` — from `contracts/channel_adapter.py`: `@runtime_checkable` Protocol with `platform` property, `verify_signature()`, `parse_messages()`, `send_response()`, `send_processing_ack()`; export `AdapterRegistry = dict[str, ChannelAdapter]`
- [X] T011 [P] Define BaseAgent Protocol in `src/chatpilot/agents/base.py` — from `contracts/base_agent.py`: `@runtime_checkable` Protocol with `name` property, `handle(message, session_id)` async method; export `AgentRegistry = dict[str, BaseAgent]`
- [X] T012 [P] Implement AgentRegistry in `src/chatpilot/agents/__init__.py` — module-level `agent_registry: AgentRegistry = {}` with helper functions `register_agent(agent)`, `get_agent(name) -> BaseAgent | None`, `list_agents() -> list[str]`
- [X] T013 Implement session manager in `src/chatpilot/sdk/session_manager.py` — `SessionManager` class wrapping `github-copilot-sdk`: `get_session_id(platform, conversation_id, user_id) -> str` (format: `"{platform}-{conversation_id or user_id}"`), `async start()` (calls `CopilotClient().start()`), `async resume_session(session_id)` returning SDK session, `async send_and_wait(session, prompt) -> str` (wraps event-based SDK into single awaitable); export singleton `session_manager`

**Checkpoint**: Foundation ready — all Protocols defined, SDK wrapper available

---

## Phase 3: User Story 1 — 透過聊天頻道與 AI Agent 對話 (Priority: P1) 🎯 MVP

**Goal**: End-to-end pipeline: LINE webhook receive → dispatcher → Copilot SDK agent → LINE reply, with 20s timeout and Pending Queue

**Independent Test**: Configure `config/routes.yaml` with one LINE group + `general-agent`; send text in that LINE group; confirm AI reply arrives within 10 seconds

- [X] T014 [P] [US1] Implement route_loader in `src/chatpilot/dispatch/route_loader.py` — `load_routes(path: str) -> RouteMap` (YAML parse + Pydantic validation with camelCase alias support), `RouteWatcher` class using `watchdog.Observer` with 200ms debounce: on file change reload and call `on_change(route_map)` callback; on parse error keep previous RouteMap and log to stderr
- [X] T015 [P] [US1] Implement Dispatcher in `src/chatpilot/dispatch/dispatcher.py` — `dispatch(message: Message, route_map: RouteMap, agents: AgentRegistry) -> tuple[DispatchResult, BaseAgent | None]` using 3-phase lookup: (1) exact `(platform, conversation_id)` match → keyword substring scan, (2) `(platform, None)` private-chat fallback rule, (3) per-rule `fallback_agent`; unmatched returns `(Ignored(), None)`
- [X] T016 [P] [US1] Implement LINE webhook parser in `src/chatpilot/channels/line/parser.py` — `parse_line_events(raw_body: bytes) -> list[Message]` using `line-bot-sdk` WebhookParser; extract `conversation_id` from `groupId or roomId or None`; filter non-text events; populate `LinePlatformContext` with `reply_token`, `message_id`, `timestamp`
- [X] T017 [US1] Implement LINE ChannelAdapter in `src/chatpilot/channels/line/__init__.py` — class `LineAdapter` implementing ChannelAdapter Protocol: `platform = "line"`, `verify_signature(raw_body, signature)` via `line-bot-sdk` `SignatureValidator`, `parse_messages(raw_body)` delegates to `parser.py`, `async send_response(message, response)` calls LINE Reply API with `response.text`（若超過 LINE 5000 字元限制則截斷，附加「…（訊息過長，已截斷）」）, `async send_processing_ack(message)` replies with "處理中，請稍候…"; export `line_adapter` singleton
- [X] T018 [P] [US1] Implement general-agent in `src/chatpilot/agents/general/__init__.py` — class `GeneralAgent` implementing BaseAgent Protocol: `name = "general-agent"`, `async handle(message, session_id)` calls `session_manager.resume_session(session_id)` then `send_and_wait(session, message.text)`; maps result to `Response`; raises `AgentError` on SDK failure; export `general_agent` singleton
- [X] T019 [P] [US1] Implement PendingMessageQueue in `src/chatpilot/queue/pending_queue.py` — class `PendingQueue`: `enqueue(session_id, content, ttl_ms)`, `dequeue(session_id) -> PendingMessage | None` (returns oldest non-expired entry, removes it), `cleanup()` (remove all expired entries); backed by `dict[str, list[PendingMessage]]`; export singleton `pending_queue`
- [X] T020 [US1] Implement webhook handler in `src/chatpilot/server/webhook.py` — FastAPI router with `POST /webhook/{platform}`: (1) look up adapter by `platform`, return 400 if not found, (2) verify signature via adapter, return 401 if invalid, (3) parse messages, (4) for each message: dequeue and send pending for same `session_id` first, then start 20s `asyncio.wait_for()` timeout, dispatch, call `agent.handle()`, send response; if timeout: call `adapter.send_processing_ack()` and enqueue agent result via background task; stdout structured log per FR-014: `[timestamp] [conversation_id] RECV text | ROUTE decision | AGENT response | ERROR stack`
- [X] T021 [US1] Implement FastAPI server in `src/chatpilot/server/__init__.py` — `create_app() -> FastAPI`: register webhook router, add `@app.on_event("startup")` to: load `.env` via `python-dotenv`, start `session_manager`, register `line_adapter` to `adapter_registry`, register `general_agent` to `agent_registry`, start `RouteWatcher`; add `@app.on_event("shutdown")` for graceful cleanup; export `app = create_app()`

**Checkpoint**: US1 complete — LINE message → Copilot SDK agent → LINE reply working end-to-end

---

## Phase 4: User Story 2 — 透過 CLI 直接與 Agent 互動 (Priority: P2)

**Goal**: Developer CLI tool that bypasses webhook server and talks directly to agent via same Copilot SDK session

**Independent Test**: Run `uv run python -m chatpilot.cli.main --agent general-agent --message "你好"`; confirm agent response printed to stdout within 10 seconds

- [X] T022 [P] [US2] Implement CLI entry point in `src/chatpilot/cli/main.py` — parse `--agent <name>`, `--message <text>`, optional `--session-id <id>` from `argparse`; load `.env`; start `session_manager`; look up agent from `agent_registry`; compute session_id as `cli-{session_id or timestamp}`; call `await agent.handle(message, session_id)`; print `response.text` to stdout; print errors to stderr with `sys.exit(1)`; use `asyncio.run()` as entry point
- [X] T023 [US2] Add CLI script to `pyproject.toml` — add `[project.scripts]` entry: `chatpilot-cli = "chatpilot.cli.main:main"` and register `general_agent` in `agent_registry` at CLI startup (without starting FastAPI server)

**Checkpoint**: US2 complete — CLI sends message to agent, receives response, no webhook server required

---

## Phase 5: User Story 3 — 路由分派將訊息導向正確 Agent (Priority: P3)

**Goal**: Dispatcher correctly routes to multiple agents by conversation_id, keyword, and per-rule fallback; unmatched messages silently ignored

**Independent Test**: Configure `config/routes.yaml` with two groups (group A → keyword "庫存" → warehouse-agent + fallback general-agent; group B → no fallback); send messages from each group and an unregistered group; verify correct routing and zero responses from unregistered group

- [X] T024 [P] [US3] Implement warehouse-agent stub in `src/chatpilot/agents/warehouse/__init__.py` — minimal class `WarehouseAgent` implementing BaseAgent Protocol: `name = "warehouse-agent"`, `async handle()` returns `Response(text=f"[warehouse-agent] 收到: {message.text}")` (stub for routing validation, no Copilot SDK call); export `warehouse_agent` singleton
- [X] T025 [US3] Register warehouse-agent and add startup route validation in `src/chatpilot/server/__init__.py` — register `warehouse_agent` to `agent_registry`; after loading routes.yaml, validate all `agent_name` and `fallback_agent` values in every `RouteRule` exist in `agent_registry`; raise `RouteError` on unknown agent name (fail fast)
- [X] T026 [US3] Add route validation on hot-reload in `src/chatpilot/dispatch/route_loader.py` — accept optional `agent_registry` param in `RouteWatcher.__init__()`; on each reload, cross-check all route agent names; if validation fails log `[ROUTE ERROR] unknown agent: {name}` to stderr and keep previous valid RouteMap
- [X] T027 [P] [US3] Enhance structured logging in `src/chatpilot/server/webhook.py` — log full dispatch decision per FR-014: `ROUTE keyword=庫存 agent=warehouse-agent` or `ROUTE fallback agent=general-agent` or `ROUTE ignored reason=no_fallback`; ensures zero AI token consumption is auditable from logs

**Checkpoint**: US3 complete — multi-agent routing validated, silent ignore auditable in logs

---

## Phase 6: User Story 4 — 新增頻道 Adapter 不影響核心 (Priority: P4)

**Goal**: Prove Ports & Adapters architecture — adding a new channel adapter requires zero changes to dispatcher, agents, or SDK layer

**Independent Test**: Send `POST /webhook/mock` with `{"text": "hello", "userId": "u1", "conversationId": "c1"}` JSON body; confirm message routed through same dispatcher and agent as LINE; confirm `src/chatpilot/dispatch/`, `src/chatpilot/agents/`, `src/chatpilot/sdk/` files have zero modifications (validates SC-004)

- [X] T028 [P] [US4] Implement MockChannelAdapter in `src/chatpilot/channels/mock/__init__.py` — class `MockAdapter` implementing ChannelAdapter Protocol: `platform = "mock"`, `verify_signature()` returns `True`, `parse_messages(raw_body)` parses JSON body as `{"text", "userId", "conversationId"}` → `list[Message]`, `async send_response(message, response)` logs `[MOCK SEND] {response.text}` to stdout, `async send_processing_ack()` logs `[MOCK ACK]`; export `mock_adapter` singleton
- [X] T029 [US4] Register MockChannelAdapter in `src/chatpilot/server/__init__.py` — add single line `adapter_registry["mock"] = mock_adapter` in `create_app()`; confirm no changes required in `src/chatpilot/dispatch/`, `src/chatpilot/agents/`, or `src/chatpilot/sdk/` (change set must be exactly 1 file: `src/chatpilot/server/__init__.py`)

**Checkpoint**: US4 complete — architecture extensibility verified, SC-004 satisfied

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Stability, observability, and production readiness across all stories

- [X] T030 [P] Add graceful shutdown to `src/chatpilot/server/__init__.py` — `@app.on_event("shutdown")`: stop `RouteWatcher` observer, stop `session_manager` CopilotClient, log `[SHUTDOWN] server stopped`
- [X] T031 [P] Create `config/routes.yaml` (gitignored, copy from `routes.example.yaml`) per `quickstart.md`; add `config/routes.yaml` to `.gitignore`
- [X] T034 [P] Add Push API configuration flag — add `PUSH_API_ENABLED` (default `false`) to `.env.example`（已含於 T005）；在 `src/chatpilot/server/__init__.py` startup 時讀取此環境變數並存入 `app.state.push_api_enabled: bool`；MVP 為 no-op（flag 存在但 push 邏輯未實作），滿足 FR-013
- [X] T035 [P] Create unit tests — `tests/conftest.py`（共用 fixtures：mock Message、mock Response、mock RouteMap）、`tests/unit/test_dispatcher.py`（3-phase lookup：keyword match、fallback、ignored、private-chat fallback）、`tests/unit/test_route_loader.py`（YAML parse、hot-reload callback、parse error keeps previous RouteMap）、`tests/unit/test_pending_queue.py`（enqueue/dequeue/expiry/cleanup）
- [X] T036 [P] Create integration + contract tests — `tests/integration/test_webhook.py`（FastAPI TestClient + httpx：POST /webhook/mock 驗證 valid/invalid signature、timeout → pending queue replay、FR-014 structured log 輸出）、`tests/contract/test_adapter.py`（驗證 MockAdapter 與 LineAdapter 滿足 ChannelAdapter Protocol 的 `isinstance` check）
- [X] T032 Validate quickstart.md E2E scenarios — follow `quickstart.md` checklist: (1) CLI smoke test `uv run python -m chatpilot.cli.main --agent general-agent --message "ping"`, (2) LINE webhook test via cloudflared tunnel, (3) hot-reload test by editing `routes.yaml` without restart; confirm all 3 pass
- [X] T033 Run `uv run pytest && uv run ruff check src/` — fix any type errors, lint warnings, or import violations before declaring implementation complete

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Requires Phase 1 completion — **BLOCKS all user stories**
- **US1 (Phase 3)**: Requires Phase 2 — no other story dependencies
- **US2 (Phase 4)**: Requires Phase 2 + US1 partial (general_agent T018, session_manager T013) — independent from US3/US4
- **US3 (Phase 5)**: Requires US1 completion (dispatcher T015, webhook handler T020)
- **US4 (Phase 6)**: Requires US1 completion (server T021, webhook handler T020)
- **Polish (Phase 7)**: Requires all desired stories complete

### User Story Dependencies

| Story | Depends On | Can Start After |
|-------|-----------|----------------|
| US1 (P1) | Phase 2 only | T013 complete |
| US2 (P2) | Phase 2 + T018 (general-agent) | T018 complete |
| US3 (P3) | US1 complete | T021 complete |
| US4 (P4) | US1 complete | T021 complete |

### Within Each User Story

- Files with no cross-dependency within the same story → [P] (implement in parallel)
- `webhook.py` (T020) depends on: dispatcher (T015), LINE adapter (T017), pending_queue (T019)
- `server/__init__.py` (T021) depends on: webhook.py (T020), route_loader (T014), all registered adapters/agents

### Parallel Opportunities

```bash
# Phase 1: All [P] tasks can run simultaneously after T001
T002 + T003 + T004 + T005 + T006

# Phase 2: All [P] tasks can run simultaneously after T008
T009 + T010 + T011 + T012 + T013

# Phase 3 (US1): [P] tasks run simultaneously
T014 + T015 + T016 + T018 + T019
# Then T017 (needs T016), T020 (needs T015+T017+T019), T021 (needs T020)

# Phase 5+6: Can start in parallel once US1 is complete
US3 tasks (T024-T027) || US4 tasks (T028-T029)

# Phase 7: [P] tasks run simultaneously
T030 + T031 + T034 + T035 + T036
# Then T032 (E2E validation), T033 (final lint + test run)
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (**CRITICAL** — blocks all stories)
3. Complete Phase 3: User Story 1 (T014–T021)
4. **STOP and VALIDATE**: Test US1 with LINE group — confirm end-to-end reply within 10 seconds
5. Deploy if validated

### Incremental Delivery

1. Phase 1 + 2 → foundation ready
2. Phase 3 (US1) → LINE webhook working → **deploy as MVP**
3. Phase 4 (US2) → CLI available for dev testing
4. Phase 5 (US3) → multi-agent routing validated
5. Phase 6 (US4) → architecture extensibility confirmed
6. Phase 7 → polish + lint

### Suggested MVP Scope

**Minimum to demonstrate value**: Phase 1 + Phase 2 + Phase 3 (T001–T021)
This delivers the complete LINE ↔ Copilot SDK ↔ LINE reply flow (SC-001, SC-003, SC-005).

---

## Summary

| Phase | Story | Tasks | Parallelizable |
|-------|-------|-------|----------------|
| 1: Setup | — | T001–T007 | T002–T006 |
| 2: Foundational | — | T008–T013 | T009–T013 |
| 3: US1 (P1) 🎯 | US1 | T014–T021 | T014–T016, T018–T019 |
| 4: US2 (P2) | US2 | T022–T023 | T022 |
| 5: US3 (P3) | US3 | T024–T027 | T024, T027 |
| 6: US4 (P4) | US4 | T028–T029 | T028 |
| 7: Polish | — | T030–T036 | T030–T031, T034–T036 |
| **Total** | | **36 tasks** | |

- [P] tasks = different files, no blocking dependencies
- [Story] label maps task to user story for traceability
- Each story is independently completable and testable
- Commit after each task or logical group of [P] tasks
- Stop at each **Checkpoint** to validate story independently
