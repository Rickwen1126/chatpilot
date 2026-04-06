# Observer VNext Spec

## Summary

observer vNext 要把目前「可用但抽象不穩」的 observer mode，重構成：

- `route_id` 作為 **storage unit**
- `route_group` 作為 **sharing/query unit**
- `binding.reply_policy` 決定回話行為
- `binding.observation` 決定背景觀察與知識消費行為

這輪的核心不是新增更多 observer special case，而是把目前混在一起的：

- registration identity
- storage identity
- query identity

正式拆開，讓後續的跨對話管理、共享背景知識與 onboarding/discovery 都有穩定基底。

## Problem

目前 observer 雖然已可用，但有三個結構性問題：

1. observer 是從 `chatbot.observer_mode` 啟動
   - registration identity 來自 chatbot config
2. observation 實際存進 `memory_observations.route_id`
   - storage identity 是 route
3. chatbot 查詢時又透過 `source label -> route_ids -> observations`
   - query identity 是另一層 synthetic source map

這導致現在的 observer：

- 看起來像一種 bot type
- 實際上卻不是 bot-level memory
- 而是 route-local storage + source-map query sharing

一旦需求成長到：

- 同一個 chatbot 在不同 route 有不同觀察/回話策略
- 多條 route 想共享同一組背景知識
- 不同 chatbot 想消費同一份背景知識

目前抽象就會開始不穩，尤其容易被 `chatbot_name` 與 source label 綁架。

## Goals

- 讓 observer 不再是一種 bot type，而是 `binding` 上的 policy
- 保持 `route_id` 為最小持久化單位，不引入 bot-level persistent memory
- 引入穩定的 `route_group` 作為共享/查詢單位
- 把回話行為從 observation/capture 抽離
- 為後續：
  - `follow/join` onboarding
  - shared memory
  - cross-platform route grouping
  提供乾淨基底

## Non-Goals

這輪刻意不做：

- `follow` / `join` discovery onboarding
- event schema 細化
- bot-level persistent memory
- `smart` reply policy 實作
- file-center / STT / recent file recall 的行為調整
- observer query API 的最終 UX 優化

## User Stories

- 作為營運群組管理者，我希望某些群組被動收集背景脈絡，但 bot 在群內保持靜默。
- 作為管理群組或私聊使用者，我希望在另一條 route 問「3 月請假狀況」或「最近物料需求」，bot 能查到同一組背景知識。
- 作為同一個 chatbot 的配置者，我希望它在不同 route 上能：
  - 在 A 群靜默觀察
  - 在 B 群被叫到才回
  - 在私聊正常回話
  而不是被迫拆成多隻 bot。
- 作為後續功能設計者，我希望 observer 的核心抽象先穩住，之後再加 onboarding/profile matching，不用再回頭拆底層 identity。

## Core Decisions

### 1. `route_id` 是 storage unit

- observation / memo / file note 仍以 route 為持久化主單位
- 不在這輪引入 bot-level persistent memory

### 2. `route_group` 是 sharing/query unit

- `route_group` 是一級配置
- 但 **不維護 `members`**
- membership 完全由 `binding.observation` 推導

### 3. `observation` 掛在 `binding`

- `chatbot` 定義 model / tools / persona
- `binding` 定義這條對話如何使用這個 chatbot
- observation 雖然像能力，但本質是 **conversation-scoped policy**

### 4. `reply_policy` 先收成兩個已實作目標

- `silent`
- `addressed`

`smart` 保留 future，不進這輪實作。

### 5. `addressed` 是比 `normal/trigger_only` 更穩的抽象

- private/direct route：通常每句都可視為 addressed
- group/shared route：依 mention / keyword / slash / 平台規則決定

所以：

- 在私聊 `addressed` 看起來像舊的 `normal`
- 在群組 `addressed` 看起來像舊的 `trigger_only`

### 6. 背景整理與互動回話是兩條 execution lane

- `reply_policy=addressed` 的互動回話，走 chatbot 的對話 session
- `observation.capture` 的背景整理，走獨立的 observation worker session
- 同一條 route 可以同時：
  - 對當前使用者訊息回話
  - 對同一批訊息做背景整理
- 但這兩件事 **不能共用同一個 session context**

理由：

- 回話 session 需要維持互動上下文與工具使用狀態
- 背景整理 session 需要套用 observation profile 的專用 instructions
- 若共用同一 session，容易發生：
  - context 汙染
  - profile prompt 混入互動回話
  - batch summarize 與即時回話互相干擾
  - 長時間 session 技術性不穩定時更難隔離問題

這裡強調的是 **execution context 分離**，不要求 observation worker 一定是長壽 session。
本輪可接受：

- 每次 batch capture 建立短生命週期 worker session
- 或未來再優化成可重用的 observation worker session

但不接受：

- 直接復用互動 chatbot session 來做 observation summarize

## Config Model

### `route_groups`

`route_group` 是正式配置物件，但先保持很薄。

最小範例：

```yaml
route_groups:
  shinyipaint_ops:
    description: 信益營運背景知識
```

這輪不放：

- `members`
- ACL
- sync config

因為這些都應該由 binding 或後續設計推導/擴充。

但本輪實作也**不要把 `route_group` 寫死成永遠只有 `description`**。

要求是：

- 目前只依賴已知最小欄位
- 不預設 `route_group` 永遠是純 label object
- 後續若要加入 retention / sync 等 group-level metadata，不應需要推翻本輪抽象

### `observation_profiles`

`observation_profile` 是 prompt-backed interpretation contract，不是 event schema。

最小範例：

```yaml
observation_profiles:
  warehouse_ops:
    mode: batch
    batch_size: 10
    instructions: |
      持續整理營運脈絡，忽略純閒聊，保留可回查、可彙總、可同步的背景知識。
```

這輪 profile 至少要支援：

- `mode`
- `batch_size`
- `instructions`

這輪不先定：

- 結構化 event schema
- downstream sync rules

### `binding.reply_policy`

最小列舉值：

- `silent`
- `addressed`

### `binding.observation`

最小 schema：

```yaml
observation:
  capture:
    group: shinyipaint_ops
    profile: warehouse_ops
  consume:
    - shinyipaint_ops
```

約束：

- `capture` 這輪只支援單一 `group + profile`
- `consume` 可為空或多個 group

## Canonical Example

```yaml
route_groups:
  shinyipaint_ops:
    description: 信益營運背景知識

observation_profiles:
  warehouse_ops:
    mode: batch
    batch_size: 10
    instructions: |
      持續整理營運脈絡，忽略純閒聊，保留可回查、可彙總、可同步的背景知識。

bindings:
  - match:
      platform: "line:shinyipaint"
      group_id: "C0069917b022d280805149bf9a8709453"
    chatbot: "shinyipaint"
    reply_policy: "silent"
    observation:
      capture:
        group: "shinyipaint_ops"
        profile: "warehouse_ops"

  - match:
      platform: "line:shinyipaint"
      group_id: "Ceead1a4ba637518e00059ac73ba2cd8a"
    chatbot: "shinyipaint"
    reply_policy: "addressed"
    observation:
      capture:
        group: "shinyipaint_ops"
        profile: "warehouse_ops"
      consume:
        - "shinyipaint_ops"

  - match:
      platform: "line:shinyipaint"
      user_id: "Ufc68d77c84b42995d970dc6639da4316"
    chatbot: "shinyipaint-admin"
    reply_policy: "addressed"
    observation:
      consume:
        - "shinyipaint_ops"
```

## Runtime Semantics

### Capture path

1. inbound route 命中 binding
2. binding 決定 chatbot + `reply_policy`
3. 若 binding 有 `observation.capture`
   - 這條 route 會成為某個 `route_group` 的 source route
   - 依 profile 做 buffer / batch observe
   - batch summarize 由獨立 observation worker session 處理
4. observation 仍存到該 route 自己的 `route_id`

### Consume path

1. chatbot 在某條 route 被 addressed
2. 若 binding 有 `observation.consume`
   - 這條 route 可查詢那些 `route_group`
3. query 時由 runtime：
   - `group -> source routes -> route-scoped observations`
4. chatbot 取得 group-level 背景知識，但 storage 仍維持 route-local

### Membership semantics

group membership **不是靜態表**，而是 binding 推導結果：

- 有 `capture.group = X` 的 route
  - 是 group `X` 的 source route
- 有 `consume = [X]` 的 route
  - 是 group `X` 的 consumer route

## Migration Strategy

### Phase 1: config schema replacement

這輪不保留舊 observer config。

舊欄位：

- `chatbot.observer_mode`
- `observer_batch_size`
- `observer_categories`
- `observer_allowed_consumers`

直接由新 schema 取代：

- `route_groups`
- `observation_profiles`
- `binding.reply_policy`
- `binding.observation`

### Phase 2: runtime rewrite

server wiring / observer registration / query path 直接改用新結構：

- 觀察能力不再從 chatbot config 啟動
- 改由 binding 上的 observation policy 啟動
- query identity 不再使用 source label

### Phase 3: query API cutover

`query_observations` 直接改為以 `group` 為 canonical API。

這輪不保留：

- source label alias
- chatbot name fallback
- 舊 observer source map UX

### Phase 4: session boundary

reply 與 capture 的 session boundary 必須一次到位：

- 互動回話不得復用 observation worker session
- observation summarize 不得復用互動 chatbot session
- runtime 可共享同一條 route 的 storage/membership 視圖
- 但不得共享同一個 session context

## Validation

### Unit / integration

- binding schema 能正確解析 `reply_policy` 與 `observation`
- `route_group` 不接受 `members`
- `addressed` 在 private/group route 的判定語意正確
- `capture` 與 `consume` membership 推導正確
- `query_observations(group=...)` 能正確展開 source routes
- observation summarize 明確走 worker session，不復用互動 chatbot session

### E2E

至少補這三組：

1. `silent` route
   - 不回話
   - 仍會 capture
   - observation row 真的落 DB

2. `addressed` route
   - 私聊：一般訊息可回
   - 群組：只有 addressed 訊息可回
   - 同時有 capture 時，回話與 summarize 仍走不同 session path

3. `capture + consume -> group query`
   - source route observation 寫入 route-local DB
   - consumer route 可以透過 group 查到
   - 非 consumer route 不能查

## Risks

- 直接替換舊 observer config 代表 migration 必須一次到位
- `addressed` 若沒有明確平台語意測試，可能在不同 adapter 上行為不一致
- 若太早把 `group` 擴成 ACL / onboarding / sync 中樞，scope 容易爆掉

## Open Questions

這份 spec 刻意保留但不在本輪拍板：

1. `route_group` 未來是否加入 retention / sync 等 group-level metadata
   - 本輪先不做
   - 但實作不得把 `route_group` 結構寫死成無法擴充
2. `follow/join` discovery onboarding 之後怎麼把 route attach 到預設 profile
3. `smart` reply policy 何時引入，以及它與 `addressed` 的優先關係

## Acceptance

這份 spec 進入 implementation 的條件是：

- config schema 與 runtime semantics 沒有再混淆 `chatbot` 與 `binding`
- `route_group` 被確認為一級配置，但不含 members
- `reply_policy = silent | addressed` 被接受為本輪最小列舉
- `binding.observation.capture.group/profile + consume[]` 被接受為本輪最小 schema
