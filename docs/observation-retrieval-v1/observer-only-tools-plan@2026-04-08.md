# Observer-Only Media Tools Plan

- Created: 2026-04-08
- Last Updated: 2026-04-08
- Status: completed

## Implementation Status

Implemented on 2026-04-08.

驗證結果：

- `uv run ruff check src/ tests/` → 綠
- `uv run pytest tests/` → `242 passed`
- `bash tests/e2e/run_e2e.sh` → `80 passed / 0 failed`

## Goal

以**最小增量**補齊 observer worker 的主動圖片理解能力，讓 capture-only route 不需要改變現場工作流程，就能把 photo-only 訊息整理進背景知識。

這輪只處理 observer lane 自己缺的能力，不擴成整體 tool access model refactor。

## Driving Use Case

`信益油漆星際總部` 這類群組需要：

- 不回話
- 不參與聊天
- 背景整理：
  - 請假
  - 出缺勤
  - 案場成果（含照片）
  - 物料需求
  - 缺料盤點

其中照片不能要求使用者一律補 caption，系統必須自己能看圖。

## Non-Goals

這輪**不做**：

- 全面的 tool audience/group refactor
- config schema 調整
- observer 與 chatbot / pipeline 的 tool access 統一重寫
- 重用 `batch_image_analyze` 這種 agent-team async pipeline
- 新的 audio 模式設計
  - audio 先沿用現有 Hub STT 路徑

## Minimal Design

### 1. 新增 `OBSERVER_ONLY`

在既有 tool access model 上只加一個最小增量：

- `OBSERVER_ONLY`

目的：

- 不動既有 `GLOBAL / CHATBOT_ONLY / AGENT_TEAM_ONLY / AGENT_TEAM_TRIGGER`
- 只讓 observer worker 能拿到一小組額外 safe tools

### 2. 新增 `ToolFactory.get_tools_for_observer()`

新增 observer lane 專用的 tool filtering：

- observer worker 可見：
  - `GLOBAL`
  - `OBSERVER_ONLY`
- chatbot lane 維持原狀
- pipeline lane 維持原狀

### 3. 新增 `observe_image_ref`

新增一個同步、純分析、無 side effect 的圖片工具：

- input:
  - `image_ref`
- output:
  - 簡潔、可落 DB 的圖片描述
  - 適合 observer worker 再整理成 fact / semantic rows

設計原則：

- 只做分析，不做回覆、不做任務提交
- 不走 agent-team async pipeline
- 讓 observer worker 自己決定何時調用

### 4. observer worker session 接上 observer tools

在 `on_observer_batch(...)` 建 observer session 時：

- 除現有 system prompt 外
- 額外掛 observer tools

這樣 observer worker 就能在看到 `[圖片 ref:...]` 時主動調用 `observe_image_ref`。

## Prompt Contract Extension

capture worker prompt 需要明確補一句：

- 若 batch 中包含圖片 ref，且圖片內容對整理事實有幫助，可使用 observer 圖片工具先取得描述
- 不可憑空猜測圖片內容
- 若圖片工具無法取得有效資訊，寧可保守略過

這代表：

- prompt 負責決策何時用工具
- tool 負責真的看圖

## Dataflow

1. message 進 Hub
2. audio 若存在，仍先走現有 STT preprocessing
3. observation lane 累積到 batch size
4. 建 observer worker session
   - 掛 observer tools
   - 注入 `observation_profile.instructions`
   - 注入 categories 與 output contract
5. worker 看到 batch 裡的 `[圖片 ref:...]`
6. worker 視需要呼叫 `observe_image_ref`
7. 用：
   - 原文字
   - 圖片分析結果
   - 已有 STT transcript
   一起整理成 batch JSON
8. dual-write：
   - `memory_observations`
   - `observation_entries`

## Implementation Slice

### Slice A — Tool Access

- `AccessLevel` 新增 `OBSERVER_ONLY`
- `ToolFactory` 新增 `get_tools_for_observer()`
- 只新增 observer lane，不動既有 chatbot / pipeline lane

### Slice B — Observer Tool

- 新增 `observe_image_ref`
- 內部可重用既有 media/file plumbing
- 保持同步、純讀取、純分析

### Slice C — Worker Wiring

- `on_observer_batch(...)` session 掛 observer tools
- worker prompt 補 tool usage contract

### Slice D — Verification

- unit:
  - observer lane tool filtering 正確
  - `observe_image_ref` 正常回結構化描述
- E2E:
  - capture-only route 丟圖片
  - log 有 `[tool_call] observe_image_ref`
  - `memory_observations` / `observation_entries` 有落表
  - route 仍維持 `reply=never + processing=none`
  - 沒有對外回話

## Success Criteria

### L1

- observer route 收到圖片訊息後不 crash

### L2

- log 明確出現 `observe_image_ref` tool call

### L3

- image batch 會落 `memory_observations` 與 `observation_entries`

### L4

- `never + none + capture` route 對外仍不回話
- photo-only 訊息也能形成可查詢的背景知識

## Follow-Up

這輪完成後，再回頭處理：

- 更完整的 tool audience/group refactor
- config-level tool group declaration
- audio-specific observer tools（若現有 STT 不足）
