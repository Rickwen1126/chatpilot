## 2026-03-06 11:29 — Architecture Refactor Complete (8/8 tasks)

**Goal**: Refactor from hardcoded `/倉管` + keyword routing into clean pipeline with `/agent` command, conversation-centric routes.yaml, and separated MessageProcessor.

**Done**:
- Brainstormed 8-point proposal → design doc at `docs/plans/2026-03-04-architecture-refactor-design.md`
- Implementation plan at `docs/plans/2026-03-04-architecture-refactor-plan.md`
- Committed pre-refactor work (session gate, warehouse agent, design docs): `7925ae5`, `83ffef4`, `4c3daaa`
- **8 tasks via subagent-driven dev, all complete** (`e64e5b3` → `c5df0ba`):
  1. New route types: `RouteConfig`, `PlatformConfig`, `ConversationRoute`
  2. `load_route_config`/`save_route_config` in route_loader
  3. `CommandHandler` with `/agent` and `/model` (unified command layer)
  4. `workdir` param added to `BaseAgent.handle()` Protocol
  5. `MessageProcessor` — clean pipeline: command → gate → route → agent → respond
  6. Wired new architecture, thinned `webhook.py` (~290 → ~35 lines)
  7. Deleted old dispatcher, keyword types, model_command (-314 lines)
  8. Final verification: 31 tests pass, ruff clean, server boots + commands work

**Decisions**:
- Keywords removed entirely — `/agent [name]` is the only way to switch agents
- routes.yaml: `agentList` (global) + `platforms.{name}.conversationRoutes` (per-conversation)
- `"null"` key in conversationRoutes = private chats; `defaultAgent` at platform level for unrouted conversations
- `/agent` switches immediately even if current agent is busy (in-flight task finishes in background)
- No transport abstraction (YAGNI) — just extracted `MessageProcessor`
- Agent backend left as-is (BaseAgent Protocol already flexible enough)
- `workdir` passed through to agent but not used yet
- RouteWatcher disabled (pending migration to new RouteConfig schema)

**State**: Branch `001-agent-gateway-mvp`, 12 commits ahead of origin. 31 tests, ruff clean. Server verified with mock adapter (`/agent`, `/model` commands work).

**Next**:
- [ ] Re-enable RouteWatcher hot-reload for new RouteConfig schema
- [ ] E2E test via LINE (server + cloudflare tunnel)
- [ ] Warehouse agent context accumulation issue (10K inventory × N turns → LLM timeout)
- [ ] Decide: merge to main or open PR

---

## 2026-03-04 03:34 — Session Gate + pending reply token fix

**Goal**: Block concurrent messages per session (session gate) + fix LINE reply token consumed by pending dequeue

**Done**:
- `src/chatpilot/server/session_gate.py` — new `SessionGate` class (is_busy/acquire/release/queue), module-level singleton
- `src/chatpilot/server/webhook.py` — restructured:
  - `/model` bypasses gate (instant command)
  - Gate wraps all other processing: acquire → `_do_process()` → release
  - `_do_process()` returns `bool` — `True` if background task spawned (gate release deferred to `_background_handle`)
  - `_release_gate()` helper handles drop notice enqueue
  - **Fixed LINE "Invalid reply token" bug**: pending messages now collected (not sent individually), combined with agent response into single reply. Old code consumed reply token per pending msg, leaving none for agent response.
- `/倉管` path now passes `model` from route rule (was always `None` → defaulting to gpt-4.1 instead of claude-haiku-4.5)
- Added step-by-step logging to warehouse agent + session_manager `send_and_wait` (still in code)
- 21 tests pass, ruff clean

**Decisions**:
- Gate release ownership: synchronous path releases in `_process_message` finally; timeout/background path releases in `_background_handle` finally
- Pending messages combined into single LINE reply (not sent individually) to avoid reply token exhaustion

**State**: Server running on port 2999 with debug logging. Branch: `001-agent-gateway-mvp`. Debug logging still in warehouse agent + session_manager. Not committed yet.

**Next**:
- [ ] Remove debug logging from warehouse agent + session_manager before commit
- [ ] Commit session gate feature
- [ ] Pre-existing issue: warehouse agent sends full 10K inventory as user message every turn, SDK session accumulates 100K+ context → causes LLM timeout. Needs architectural fix (separate from gate work).

---

## 2026-03-03 23:49 — 全 MVP 實作完成 (36/36 tasks)

**Goal**: 將 `001-agent-gateway-mvp` 從設計文件實作為完整可運行的 Python 專案

**Done**:
- `/speckit.clarify` 全部 5 題完成，答案已寫入 spec.md
- 研究 GitHub Copilot SDK session 模型
- Spec 新增 FR-014，共 14 條 FR
- `/speckit.plan` + 技術棧切換 + `/speckit.analyze` + 全部 findings 修復
- **`/speckit.implement` 完成 — 全部 36 tasks, 7 phases**:
  - Phase 1: uv project, pyproject.toml, directory tree, .env.example, routes.example.yaml
  - Phase 2: core types (Pydantic v2), errors, ChannelAdapter/BaseAgent Protocols, AgentRegistry, SessionManager
  - Phase 3 (US1): route_loader + watchdog hot-reload, dispatcher 3-phase lookup, LINE parser/adapter, general-agent, pending queue, webhook handler, FastAPI server
  - Phase 4 (US2): CLI tool (`chatpilot-cli`)
  - Phase 5 (US3): warehouse-agent stub, route validation on startup + hot-reload
  - Phase 6 (US4): MockAdapter — zero core changes proves Ports & Adapters
  - Phase 7: 21 tests (6 dispatcher + 3 route_loader + 5 pending_queue + 3 webhook + 4 contract), ruff clean
- Committed: `d342680` — 51 files, 4624 insertions
- LINE Official Account 回應設定確認正確（Webhook ON, 自動回應 OFF, 聊天 OFF）
- Cloudflare tunnel: `bot.webric.dev` → scene-advisor tunnel, port 2999
- `.env.example` PORT 改為 2999
- **E2E 測試通過**: LINE → ChatPilot → Copilot SDK → LINE reply 全流程確認
- Bug fix: `SessionManager.resume_session` 需傳 `PermissionHandler.approve_all`（`src/chatpilot/sdk/session_manager.py:49`）
- `config/routes.yaml` 簡化為僅 private chat + mock 路由（移除不存在的 `report-agent` 避免啟動 crash）
- Mock adapter 本地測試通過：Copilot SDK 回應 "1+1 = 2."

**Decisions**:
- Language: Python 3.11+ / FastAPI / uv / Pydantic v2 / Protocol / pytest / ruff
- Port: 2999（避免與 onduty 3000 衝突）
- `line-bot-sdk` v3 import: `WebhookParser` from `linebot.v3`（非 `linebot.v3.webhooks`）
- LINE Channel Access Token 需在 LINE Developers Console > Messaging API tab 底部手動 Issue

**State**: E2E 測試通過。Branch: `001-agent-gateway-mvp`。有未 committed 的修正（PermissionHandler fix + routes.yaml 簡化）。

**Next**:
- [ ] Commit E2E 修正（session_manager PermissionHandler + routes.yaml cleanup）
- [ ] 決定是否 merge 到 main 或開 PR
