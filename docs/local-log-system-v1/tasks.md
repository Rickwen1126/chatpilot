# Local Log System V1 Tasks

- Created: 2026-04-08
- Last Updated: 2026-04-08
- Status: completed

## Phase 1 — Foundation

- [x] T001 新增 logging config schema，讓 `route_settings.yaml` 可定義 `enabled / dir / level / max_bytes / backup_count`
- [x] T002 建立 logging backend interface，確立 V1 backend 可先用 write-file、未來可替換
- [x] T003 建立 file backend，支援：
  - 單一 current file
  - size-based rotation
  - timestamp archive naming
- [x] T004 startup 時初始化 local logging，不再只靠 shell redirect
- [x] T005 config reload 時若 logging config 改變，能安全重新套用

## Phase 2 — Log Contract

- [x] T010 定義 formatter contract：timestamp / level / logger / file:line / message
- [x] T011 保留 Copilot SDK `[SDK]` / `[event]` 原生日誌，不做語意破壞
- [x] T012 補 route-centric correlation：
  - `route_id`
  - `target_route_id`
  - `sdk_session_id`
  - `task_id`
  - `schedule_id`
  - `tool_name`

## Phase 3 — Core Module Rollout

- [x] T020 收斂 `server/webhook.py` / `routing/router.py` / `hub/hub.py` 的主要 dataflow log
  - 備註：既有高訊號 log 已足夠，這輪主要把它們納入新的 file backend 與 E2E matcher，不額外重寫 call site
- [x] T021 收斂 `chatbot/manager.py` / `chatbot/session.py` 與 `sdk/session.py` 的橋接 log
- [x] T022 收斂 `cron/scheduler.py` / `schedule_agent.py` / `memory/store.py` 的關鍵狀態 log

## Phase 4 — Validation

- [x] T030 `.gitignore` 忽略 `log/`
- [x] T031 新增 unit tests：
  - config parse
  - file backend write
  - rotation / backup count
- [x] T032 跑 `uv run ruff check src/ tests/`
- [x] T033 跑 `uv run pytest tests/`
- [x] T034 補一條 focused verification：
  - startup 後自動建立 `log/`
  - `chatpilot.log` 可寫入
  - rotation 正常

## Verification Snapshot

- `uv run ruff check src/ tests/`
- `uv run pytest tests/ -q` → `248 passed`
- `bash tests/e2e/run_e2e.sh` → `82 passed / 0 failed`
