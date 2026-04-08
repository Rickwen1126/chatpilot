# Local Log System V1 Spec

- Created: 2026-04-08
- Last Updated: 2026-04-08
- Status: completed

## Summary

chatpilot 需要一套 **app 內建、config-driven、local-first** 的 logging system。

這輪定案：

- raw log 不進 SQLite
- 不依賴外部 shell redirect 或部署 pipeline
- 單一 current log file 為主，rotation 只為控制檔案大小
- log 要以 `route_id` 為主關聯鍵，讓人能直接從 log 看出 dataflow / tool calling / state transition
- logging backend 必須先抽象化，V1 backend 用 write-file，未來可替換成 Elasticsearch / Loki / cloud logging

## Problem

目前 chatpilot 的 logging 有三個缺口：

1. app 內只有 `logging.basicConfig(...)`
   - live `2999` 可用的 log 其實仰賴外部 shell redirect
   - 不是 app 內建能力

2. log 雖然已有不少高訊號事件，但缺少明確的全域 contract
   - 不同模組寫法不完全一致
   - `route_id` / `target_route_id` / `task_id` / `session_id` 不是一套穩定規則

3. 之後要做長期 self-check 與持續觀察
   - 若 log 不能清楚反映 call stack / dataflow
   - debug 與 audit 成本會很高

## Goals

- 建立 app 內建 local logging system
- logging 由 config 控制：
  - enable / disable
  - dir
  - level
  - max_bytes
  - backup_count
- raw log 固定落在 repo-local `log/`
- rotation 控制檔案大小，避免單檔爆炸
- log 內容可以直接看出：
  - caller route
  - target route
  - tool chain
  - major state transition
- logging backend 抽象化，未來可換外部系統

## Non-Goals

這輪不做：

- Elasticsearch / Loki / cloud logging backend
- log dashboard
- log search UI
- metrics / tracing / OpenTelemetry 全套 observability
- log table / SQLite raw log storage

## Core Decisions

### 1. raw log 不進 DB

SQLite 只存結構化業務資料，例如：

- `memory_*`
- `tasks`
- future health-check structured report

raw execution trace 不進 DB。

原因：

- raw log 查詢與保留策略和業務資料不同
- 之後若要集中化，應接專門的 log backend

### 2. 單一 current log file 為主

V1 不靠多檔分類。

預設只維持：

- `log/chatpilot.log`

分類靠：

- `level`
- `tag`
- `logger`
- `key=value` structured context

而不是靠：

- `observer.log`
- `scheduler.log`
- `tool.log`

rotation 只為控 size，不是分類手段。

### 3. local `log/` 目錄，不進 git

V1 raw log 固定落在 repo root：

- `log/`

這個目錄：

- app startup 自動建立
- 不進 git
- 適合本地長期運行與 `tail -f`

### 4. route-centric correlation model

chatpilot 的 log 主關聯鍵不是單純 request id，而是：

- `route_id`

因為：

- route 是對話主體
- route 是 binding / policy / capture / consume / query scope 的核心單位

若有跨 route 行為，必須能同時看到：

- `route_id`：誰發起
- `target_route_id`：查誰 / 操作誰

### 5. logging backend 必須可抽換

V1 不直接把 logging 寫死在 file handler。

應抽出一層 backend interface，例如：

- `LoggingBackend`

V1 backend：

- write-file backend

未來可替換：

- Elasticsearch backend
- Loki backend
- cloud logging backend

但上層 log contract 不應因此改變。

### 6. Copilot SDK session log 必須保留原汁原味

chatpilot 目前最有價值的 debug 能力之一，是：

- `src/chatpilot/sdk/session.py` 直接把 Copilot SDK session 的 lifecycle
- prompt send / wait
- response preview
- event stream
- tool call / tool result

以 `[SDK]` 與 `[event]` 形式打出來。

V1 原則：

- **不重寫、不隱藏、不過度包裝這條 log**
- 不把 Copilot SDK session log 降級成只有高層摘要
- 不把原始 session debug 能力抽象到看不出 SDK 行為

原因：

- 這條 log 是 chatpilot 與一般代理工具拉開差距的重要 debug 資產
- 許多 tool-routing、timeout、resume/recreate、response drift 問題，只有 SDK session log 最快看得懂

### 7. 對 Copilot SDK session log 做「橋接」，不是「取代」

V1 不要求改寫 SDK session log 本身。

正確做法是：

- **保留既有 `[SDK]` / `[event]` log 原樣**
- 另外讓 chatpilot 上層 log 能把：
  - `route_id`
  - `chatbot`
  - `task_id`
  - `schedule_id`
  - `caller_kind`
  - `target_route_id`
  和對應的 `sdk_session_id` 串起來

也就是：

- SDK log 保留「session runtime 細節」
- chatpilot log 補「業務語意與關聯鍵」

而不是要求 SDK 那層自己知道全部業務欄位。

## Required Log Contract

### Base fields

每條重要 log 至少應包含：

- timestamp
- level
- logger name
- `filename:lineno`
- tag
- event
- description

### Context fields

依事件性質補齊：

- `route_id`
- `target_route_id`
- `group`
- `profile`
- `chatbot`
- `session_id`
- `sdk_session_id`
- `task_id`
- `schedule_id`
- `tool_name`
- `tool_call_id`

若事件與 Copilot SDK session 有關，還應能透過相同 `sdk_session_id` 與上層 route/task log 對應起來。

## Copilot SDK Log Bridging

### Preserve

以下型別的 log 應繼續保留，且盡量維持原本語意：

- `[SDK] ... sending`
- `[SDK] ... attachments`
- `[SDK] ... got result`
- `[SDK] ... response`
- `[SDK] ... timeout`
- `[SDK] ... failed`
- `[event] ... tool_call`
- `[event] ... tool_result`
- `Created SDK session ...`
- `Resumed SDK session ...`

這些訊息不應被新的 logging abstraction 吃掉或改寫得過於抽象。

### Bridge

需要補的不是重寫 SDK log，而是讓以下上層 log 穩定存在：

- `Session setup route=... chatbot=... model=... tools=...`
- `Created/Resumed route=... chatbot=...`
- `[Chatbot] ... session=...`
- `[schedule-agent] ... target_route=...`
- `[observer] ... session=... route_id=... profile=...`

這樣一來，debug 時可以用：

1. `route_id`
2. `sdk_session_id`
3. `task_id` / `schedule_id`

三層關聯把高層 dataflow 與低層 SDK runtime 串起來。

### Design rule

對 Copilot SDK logging 的設計原則是：

- **retain native signal**
- **add correlation**
- **avoid rewriting semantics**

也就是：

- 盡量保留原本 SDK session log 的 wording 與粒度
- 在 chatpilot 上層補關聯與 context
- 不為了形式統一而犧牲可用的原生 debug 訊號

### Message style

log 應偏向：

- 短描述 + key=value

例如：

```text
2026-04-08 15:30:12,345 INFO [chatpilot.hub] hub.py:214 [hub] event=terminal_drop route_id=line:... reply=never processing=none capture=true
```

而不是只寫模糊 prose。

## Mandatory Boundary Events

V1 要求以下邊界一定有高訊號 log。

### A. inbound path

- webhook received
- parser parsed
- router resolved
- hub lane decision

### B. chatbot path

- chatbot send / got response
- SDK session create / resume / destroy
- SDK send / wait / response / timeout
- tool call
- tool result

### C. observer path

- message buffered
- batch start
- media inspect start/result
- batch saved

### D. scheduler path

- cron trigger
- schedule-agent delegated
- delegated SDK session create / resume / destroy
- task completed / failed

### E. persistence path

- DB save/update on major state transitions
- degraded / partial save

## Log Levels

### INFO

寫主要 state transition：

- route resolved
- terminal drop
- tool called
- observation batch saved
- task completed

### DEBUG

寫 decision detail：

- shortlist scoring detail
- branch decision
- payload preview
- retry / fallback reason

### WARNING

寫 degraded path：

- fallback
- partial success
- stale state
- projection mismatch

### ERROR

寫 failed path：

- exception
- hard failure
- irreversible error

## Rotation Policy

V1 採 size-based rotation。

### current file

- `log/chatpilot.log`

### rotated files

建議保留明確時間後綴，例如：

- `log/archive/chatpilot@2026-04-08T15-30-00.log`

### config knobs

- `enabled`
- `dir`
- `level`
- `max_bytes`
- `backup_count`

## Suggested Config Shape

V1 可先放在 `route_settings.yaml` 的 app-level 區塊，例如：

```yaml
logging:
  enabled: true
  dir: log
  level: INFO
  max_bytes: 20971520
  backup_count: 10
```

這只是 V1 建議，不代表未來不能獨立成另一份 logging config。

## Security / Redaction Rules

log 不可直接打出：

- access token
- reply token
- secret / API key
- 大段原始敏感內容

若需要 debug payload：

- 用 summary
- 用 preview
- 用 id / ref

避免整包原文落 log。

## Relationship to Self-Check

self-check 是獨立功能，不是 log system 的一部分。

但 self-check 會依賴這套 log system 做：

- raw execution trace
- call stack audit
- route-level dataflow debug

structured self-check result 仍應落在：

- `tasks.db`

raw trace 則留在：

- `log/chatpilot.log`

## Success Criteria

- live 運行不再依賴 shell redirect 才有穩定 log
- `log/` 自動建立，並且不進 git
- 單一 current log file 可長期運行
- rotation 能控 size
- 重要 dataflow 可以從 log 讀出：
  - caller route
  - target route
  - tool chain
  - state transition
- logging backend interface 已被定義為可替換
