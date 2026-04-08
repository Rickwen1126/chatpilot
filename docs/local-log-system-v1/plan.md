# Local Log System V1 Plan

- Created: 2026-04-08
- Last Updated: 2026-04-08
- Status: completed

## Goal

在不破壞現有 debug 體驗的前提下，把 chatpilot 的 logging 從：

- `basicConfig(...)`
- 外部 shell redirect

收斂成：

- app 內建
- config-driven
- local-first
- route-centric
- backend 可替換

的 log system。

## Scope

### In scope

- logging backend interface
- write-file backend（V1）
- config schema（最小 logging 區塊）
- local `log/` 目錄管理
- size-based rotation
- formatter contract（timestamp / level / logger / file:line / tag / key=value）
- route-centric correlation fields
- Copilot SDK log bridging
- 核心模組 logging contract 收斂

### Out of scope

- Elasticsearch / Loki / cloud logging backend
- dashboard / search UI
- metrics / tracing / OpenTelemetry
- health-check implementation
- log retention 外部清理策略 beyond backup_count

## Design Principles

### 1. Preserve native Copilot signal

`src/chatpilot/sdk/session.py` 既有的：

- `[SDK]`
- `[event]`

是核心 debug 資產。

V1 不重寫它的語意，只補 correlation。

### 2. Route-centric first

log 的主關聯鍵是：

- `route_id`

若行為跨 route：

- `target_route_id`

必須可見。

### 3. Single current file

V1 只有一條 current raw log file：

- `log/chatpilot.log`

rotation 只是控 size。

### 4. Backend abstraction first

先抽象 backend，再落 write-file。

避免未來接外部系統時重寫整個 logging call site。

## Proposed Architecture

### A. Logging config

先在 app config 增加最小 logging 區塊，例如：

```yaml
logging:
  enabled: true
  dir: log
  level: INFO
  max_bytes: 20971520
  backup_count: 10
```

V1 可先掛在 `route_settings.yaml` 的 app-level 區塊。

### B. Logging backend interface

定義一個最小 backend interface，例如：

- `emit(record)`
- `flush()`
- `close()`

V1 backend：

- file writer backend

future backend：

- Elasticsearch
- Loki
- cloud logging

### C. File layout

V1：

- current:
  - `log/chatpilot.log`
- rotated:
  - `log/archive/chatpilot@YYYY-MM-DDTHH-MM-SS.log`

### D. Formatter contract

每條重要 log 至少輸出：

- timestamp
- level
- logger name
- `filename:lineno`
- tag
- event
- key=value context

## Correlation Model

### Required correlation keys

- `route_id`
- `target_route_id`（若有）
- `sdk_session_id`
- `task_id`
- `schedule_id`
- `tool_name`
- `chatbot`
- `group`
- `profile`

### Bridging rule

上層 chatpilot log 要能把：

- route/business context

與：

- Copilot SDK session runtime log

透過共同 `sdk_session_id` 串起來。

## Mandatory Modules for V1

V1 不要求全 repo 一次洗完。

先收斂核心 dataflow 熱區：

1. `server/webhook.py`
2. `routing/router.py`
3. `hub/hub.py`
4. `server/__init__.py`
5. `chatbot/manager.py`
6. `chatbot/session.py`
7. `sdk/session.py`
8. `tools/factory.py`
9. `cron/scheduler.py`
10. `pipeline/samples/schedule_agent.py`
11. `memory/store.py`

## Implementation Phases

### Phase 1 — Backend + config foundation

- 加 `logging` config schema
- 建立 logging backend interface
- 建立 file backend
- startup 時初始化 `log/`
- app 改成內建 file logging，不再依賴 shell redirect

### Phase 2 — Formatter + rotation

- 實作 formatter contract
- 實作 size-based rotation
- rotated file naming 採 timestamp suffix
- `.gitignore` 忽略 `log/`

### Phase 3 — Core correlation rollout

- 在核心模組補齊 route-centric correlation fields
- 補 `target_route_id`
- 補 `sdk_session_id` 橋接
- 確保關鍵邊界事件都有高訊號 log

### Phase 4 — Copilot SDK log bridging audit

- 確認 `[SDK]` / `[event]` 原生日誌仍存在
- 確認上層 session / route / task log 能串到這些 session ids
- 避免新 abstraction 吃掉現有 debug signal

## Validation

### L1

- app 啟動後自動建立 `log/`
- `log/chatpilot.log` 存在且有內容

### L2

- rotate 後 current file 仍持續寫入
- archive naming 正確

### L3

- 以一條真實路徑驗證：
  - inbound message
  - router
  - hub
  - chatbot / observer
  - tool call
  - DB save

log 中可追出完整 dataflow

### L4

- observation retrieval 或 self-check 這類跨 route / 跨 tool 路徑
- log 中可同時看出：
  - caller route
  - target route
  - sdk session
  - tool chain

## Success Criteria

- live debug 不再需要 shell redirect 才有穩定 log
- 單一 current file 足夠支撐日常 tail / grep
- route-centric dataflow 可從 log 直接讀出
- Copilot SDK 原生日誌未被削弱
- backend interface 已就位，未來可換外部系統
