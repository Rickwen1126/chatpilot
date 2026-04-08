# Observation Self-Check V1 Spec

- Created: 2026-04-08
- Last Updated: 2026-04-08
- Status: active

## Summary

這輪要定義一個最小可用的 **scheduled self-check**：

- 定期確認 observation 資料有沒有正常進來
- 定期確認自然語言查詢是否仍能命中正確知識
- 直接沿用現有：
  - `CronScheduler`
  - `schedule-agent`
  - `bot 測試`
  - `shinyipaint`
  - observation retrieval tools

這輪不把它擴成完整監控平台，也不先做 log system spec。

## Problem

目前 observation / retrieval 雖然已能運作，但缺少一條**定期自我檢測**的守護路徑：

1. capture 可能因 quota、prompt drift、worker timeout、projection bug 而失效
2. retrieval 可能因資料量增加、時間語意漂移、tool routing 改變而退化
3. 現在大多靠人工 smoke test，沒有長期、可回顧、可排程的健康檢查

## Goals

- 建立一個可排程的 observation self-check
- 同時覆蓋：
  - capture / projection freshness
  - semantic retrieval correctness
- 結果能留下 durable history
- semantic probe 採用 **單次大 request**，符合 Copilot request 使用準則

## Non-Goals

這輪不做：

- local log system spec / implementation
- 外部 observability backend
- 主動推播 / system broadcast
- dashboard UI
- 跨 project / 跨 process watchdog

## Core Decisions

### 1. self-check 用現有 scheduler，不另開系統

V1 直接沿用：

- `memory_schedules`
- `CronScheduler`
- `schedule-agent`

不新增另一套排程框架。

### 2. self-check 分成兩段

#### A. deterministic preflight

目的：

- 確認 capture / projection 是否仍健康

至少檢查：

- 指定 group 底下各 source route 最近是否有新 `memory_observations`
- 最近是否有對應的 `observation_entries`
- 是否出現明顯 stale / empty / projection mismatch

#### B. semantic probe

目的：

- 確認自然語言查詢仍然查得到正確知識

probe 採用：

- 既有 consume route：`bot 測試`
- 既有 chatbot：`shinyipaint`
- 既有 tools：
  - `list_observation_candidates`
  - `query_observation_member`

### 3. semantic probe 用單次大 request

V1 明確規定：

- 不把 probe 問題拆成多個一來一回的小 prompt
- 每次 self-check 的 semantic probe 應用**單次大 request**完成

這個 request 內要一次交代：

- probe queries
- must-hit facts
- forbidden drift
- 輸出格式

### 4. V1 先用 task history 存結果

結果落在：

- `data/tasks.db` 的 `tasks` table

至少要保存：

- summary pass/fail
- full structured report
- error / degraded reason

raw execution trace 不在這份 spec 內定義；這輪只要求 task history 可回看。

### 5. V1 不要求主動通知

這輪先做：

- scheduled execution
- task history result

不要求：

- 主動推播到 admin route
- 群組通知
- 告警 escalation

## Proposed Runtime Shape

### Scheduled task input

一筆 self-check schedule 至少要有：

- target consume route（預設 `bot 測試`）
- target group（例如 `shinyipaint_ops`）
- probe query list
- must-hit / forbidden drift rubric
- freshness window

### Execution flow

1. scheduler 觸發 `schedule-agent`
2. 先做 deterministic preflight
3. 再做單次大 request semantic probe
4. 產出 structured report
5. 存到 `tasks`

## Suggested V1 Tooling

V1 建議新增一個 deterministic health snapshot tool，例如：

- `observation_health_snapshot`

用途：

- 給 semantic probe 前的 preflight 使用
- 不依賴 LLM 推理
- 回傳 route freshness / entry count / stale status 等結構化資料

semantic probe 則沿用既有工具，不另開新 retrieval tool。

## Suggested Probe Style

每次排程的 semantic probe 建議 2-5 題固定 probe，例如：

- `4/10 誰請假？`
- `林有仁今天交代盤點什麼？`
- `瑞安最近缺什麼料？`

每題都要定義：

- must-hit facts
- allowed context
- forbidden drift

V1 不要求逐字比對回答，只要求：

- 有命中核心事實
- 沒有嚴重時間漂移 / 來源漂移

## Success Criteria

- 能定期自動執行
- 結果能在 `tasks` 回看
- semantic probe 使用單次大 request
- 至少能明確區分：
  - capture/projection stale
  - retrieval semantic drift
  - schedule execution failure
