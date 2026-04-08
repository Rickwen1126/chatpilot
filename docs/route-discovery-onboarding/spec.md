# Route Discovery Onboarding Spec

- Created: 2026-04-07
- Last Updated: 2026-04-08
- Status: completed

## Summary

這個功能要把 route discovery 從現在的 **message-driven discovery**，提升成 **pre-message onboarding**：

- LINE `follow` 事件可先發現私聊 route
- LINE `join` 事件可先發現群組 route
- discovery 當下就能：
  - 建立 canonical `route_id`
  - 反查名稱/標籤
  - 套用預先設定好的 discovery profile
  - 在第一則真正 message 前就把 route 放進正確、安全的初始狀態

這輪的目標不是做完整的 observer/referral/reflex 系統，而是把「bot 被加入好友或群組後，要怎麼被安全、漂亮地接進系統」這條 path 定穩。

## Problem

目前 route discovery 幾乎只能靠第一則 `MessageEvent`：

- LINE parser 只處理 `MessageEvent`
- bot 被加入群組或被加好友時，不會先建立 route
- 若想把某條新 route 預設成 observer / silent / 特定 chatbot，就得等第一則訊息進來

這會導致幾個問題：

1. **第一則 discovery message 綁架行為**
   - 系統還沒套 profile
   - 新群組第一則訊息可能先走 fallback bot 或預設 reply path
   - 高風險情境下容易先亂回一句

2. **無法在 message 前完成 onboarding**
   - 無法先套 route-level policy
   - 無法先把 route 對應到特定 chatbot / observation / reply policy
   - 無法先補 label 與管理介面可見性

3. **observer / onboarding 需求被 route discovery 卡住**
   - 使用者往往是帶著明確目的把 bot 拉進群組
   - 但系統目前無法在加入當下就把該目的體現在 route policy 上

## Goals

- 支援 LINE `follow` 與 `join` 的 pre-message route discovery
- discovery 事件本身不進一般 chatbot reply flow
- 在 discovery 當下建立 canonical `route_id`
- discovery 當下就能做 label enrichment
- 用 config 中的 discovery rule / profile 對新 route 套用預設 route policy
- 預設策略安全：
  - 新群組預設不回話
  - 私聊 discovery 本身不回話；真正聊天從第一則 user message 開始
- 讓 onboarding state 成為後續：
  - observer / route_group
  - route-level audio mode
  - route-level recent file recall
  - group 記憶匯入
  的穩定前置能力

## Non-Goals

這輪不做：

- `memberJoined` 或更完整的群成員同步
- discovery 階段直接建立/啟動 chatbot session
- 完整的 admin UI
- 以 discovery 規則做高風險授權判定
- `follow/join` 的完整 E2E 自動化（先留後續）
- observer `shadow` mode
- 匯入 group 記憶資料本身

## User Stories

- 作為系統管理者，我希望 bot 一被加入群組，就先被發現並套上正確的安全預設，而不是等第一則訊息才知道它存在。
- 作為信益油漆的使用者，我希望新群組如果名稱符合預先設定的模式，bot 在加入當下就被設定成對應 profile，例如靜默觀察或特定助手。
- 作為管理者，我希望私聊 route 在使用者加好友後就先被建立，這樣我能在真正聊天前就看到這條 route。
- 作為後續功能開發者，我希望 onboarding state 能和 static binding 共存，不必把所有動態 route 都硬寫進靜態 `bindings`。

## Core Decisions

### 1. Discovery 與 Conversation 要分開

`follow` / `join` 是 **discovery events**，不是 conversation events。

這代表：

- discovery event 不進一般 chatbot reply flow
- discovery event 不建立互動 session
- discovery event 的主要責任是：
  - route discovery
  - label enrichment
  - route onboarding state materialization

### 2. Discovery 當下要建立 canonical `route_id`

一旦 webhook 驗證出 named LINE adapter，就已經知道：

- channel identity，例如 `line:shinyipaint`
- `user_id` 或 `group_id`

因此 discovery 當下就能建立：

- `line:shinyipaint:U...`
- `line:shinyipaint:C...`

不需要等第一則 `MessageEvent`。

### 3. Dynamic Route Onboarding State 是 runtime route policy

這輪新增一層 **dynamic route onboarding state**：

- 它不是 session
- 不是 chatbot override 本身
- 也不是把新 route 寫回 static `bindings`

它的角色是：

- 當 discovery event 命中某條 rule 時
- 對這條新 route materialize 一份 route-level runtime policy

這份 policy 至少可包含：

- `chatbot`
- `reply_policy`
- `processing_policy`
- `observation`
- 後續可擴充的 route-level metadata

### 4. Discovery Profile 是 route policy template

要預先定義一組或多組 discovery profile。

每個 profile 本質上是一個 route onboarding template，可包含：

- `chatbot`
- `reply_policy`
- `processing_policy`
- `observation`

這些 profile 不是 chatbot type，也不是 observer mode，而是：

**bot 被加入某條新 route 時，應如何初始化這條 route。**

### 5. Discovery Rule 負責選 profile

discovery rule 的角色是：

- 在 `follow/join` 發生時
- 根據 route 當下已知資訊
- 選出要套用哪個 profile

這輪可支援的 matching 類型：

- exact `group_id`
- exact `user_id`
- label keyword match
- channel default
- global default

推薦 precedence：

1. exact id
2. label keyword
3. channel default
4. global default

### 6. 群組名稱 keyword match 只做 onboarding convenience，不做高風險授權

群組名/私聊顯示名稱是最實用的 onboarding signal，但不應拿來做高風險授權。

因此這輪的定位是：

- **可以用於預設 profile onboarding**
- **不可以當作高風險授權依據**

高風險情境若需要更強保證，後續仍應轉成 exact `group_id` / `user_id`。

### 7. 安全預設：群組偏保守、私聊偏便宜

這輪預設策略如下：

#### 新群組

- discovery 當下預設不回話
- 預設應偏向安全策略，例如：
  - `reply_policy = never`
  - `processing_policy = none`
- 若命中特定 rule，可進一步套：
  - observer/capture profile
  - 特定 chatbot

#### 新私聊

- discovery event 本身不回話
- 但可預設配置較便宜的 interactive chatbot，供第一則真正 user message 使用
- 也就是：
  - discovery 階段只做 route 建立與 profile 套用
  - 真正聊天從第一則 message 開始

### 8. Label enrichment 是 discovery 的一部分

discovery 當下應盡量完成名稱反查：

- `join` 後用 LINE group summary / member count 取得群名
- `follow` 後用 LINE profile 取得使用者顯示名稱

label 不是附屬功能，而是 onboarding 的一部分，因為：

- keyword matching 需要它
- admin route catalog 需要它
- 使用者需要看得懂 route

### 9. Discovery onboarding 是 snapshot semantics

discovery profile / rule 的套用時機，是 **route 被發現的當下**。

這代表：

- `follow` / `join` 命中哪個 profile，會 materialize 成該 `route_id` 的 onboarding state
- `/cli/reload` 讀到新的 disk config，只會影響**未來新發現**的 routes
- 已經 discovery 過的 route，不應因為單純 reload 而被重新套用新 profile

如果未來需要：

- 重新依新 config 對已 discovery route 做 reconcile
- 或手動重套 profile

那應作為另一個明確功能，而不是隱含在 `reload` 裡。

### 10. unmatched discovery event 仍保留 hard fallback

這輪雖然支援：

- exact id
- label keyword
- channel default
- global default

但 runtime 仍應保留 hard fallback，避免 config 漏配時 discovery event 整條消失。

最小 hard fallback：

- new group → `reply_policy=never`、`processing_policy=none`
- new private route → `reply_policy=addressed`、`processing_policy=interactive`

chatbot 優先使用 `buddy`；若不存在，再退回第一個可用 chatbot。

## Proposed Config Model

### `discovery_profiles`

```yaml
discovery_profiles:
  default_group_safe:
    chatbot: buddy
    reply_policy: never
    processing_policy: none

  shinyipaint_ops_observer:
    chatbot: shinyipaint-observer
    reply_policy: never
    processing_policy: none
    observation:
      capture:
        group: shinyipaint_ops
        profile: warehouse_ops

  default_private_cheap:
    chatbot: buddy
    reply_policy: addressed
    processing_policy: interactive
```

### `discovery_rules`

```yaml
discovery_rules:
  - platform: line:shinyipaint
    route_type: group
    group_id: C0069917b022d280805149bf9a8709453
    profile: shinyipaint_ops_observer

  - platform: line:shinyipaint
    route_type: group
    label_keywords: ["信益", "油漆", "倉庫"]
    profile: shinyipaint_ops_observer

  - platform: line:shinyipaint
    route_type: group
    profile: default_group_safe

  - platform: line:shinyipaint
    route_type: user
    user_id: Ufc68d77c84b42995d970dc6639da4316
    profile: shinyipaint-admin

  - platform: line:shinyipaint
    route_type: user
    profile: default_private_cheap
```

## Runtime Dataflow

### A. `join` 群組 discovery

1. webhook 收到 LINE `join`
2. 驗證 signature，決定 named adapter（例如 `line:shinyipaint`）
3. 建立 canonical route：
   - `line:shinyipaint:C...`
4. 反查 group summary / member count，補 label
5. 用 discovery rules 選 profile
6. materialize dynamic route onboarding state
7. 不進 chatbot reply flow，不回話

### B. `follow` 私聊 discovery

1. webhook 收到 LINE `follow`
2. 驗證 signature，決定 named adapter
3. 建立 canonical route：
   - `line:shinyipaint:U...`
4. 反查 profile display name，補 label
5. 用 discovery rules 選 profile
6. materialize dynamic route onboarding state
7. 不進 chatbot reply flow，不回話

### C. 第一則真正 message

第一則 `MessageEvent` 進來時：

- route 已經存在
- label 可能已經存在
- discovery profile 可能已經先套上

因此這則 message：

- 不會再走「尚未 discovery 的 fallback 世界」
- 而是直接按照已套好的 route policy 進 Hub / routing / observation path

## Functional Requirements

1. 系統必須支援 LINE `follow` 事件做 pre-message private route discovery。
2. 系統必須支援 LINE `join` 事件做 pre-message group route discovery。
3. discovery 事件必須能建立 canonical route identity，而不必等待第一則 message。
4. discovery 事件不得進一般 chatbot reply flow。
5. 系統必須支援 config-driven discovery profiles。
6. 系統必須支援 config-driven discovery rules，至少包含 exact id、label keyword、channel default、global default。
7. 系統必須在 discovery 當下完成 label enrichment（若平台 API 可用）。
8. 系統必須能在 runtime 保持 dynamic route onboarding state，供第一則 message 直接沿用。
9. 群組 route 在沒有更特別規則時，必須採用安全預設，不先回話。
10. 私聊 route discovery 本身不得回話；真正回話從第一則 user message 開始。
11. discovery keyword matching 只能用於 onboarding convenience，不得被定義成高風險授權機制。
12. `/cli/reload` 對 discovery onboarding 採 snapshot semantics；它不會重套已 discovery route 的 profile。
13. 若 config 漏配 discovery rule，runtime 仍必須有 hard fallback，避免 route 在 discovery 當下消失。

## Success Criteria

- bot 被加好友或加進群組後，管理者可在不發第一則訊息的前提下，在 admin route catalog 中看到新 route。
- 新群組在第一則 message 前，就能套上正確的 route onboarding policy，不會先意外回話。
- 命中預設群組名稱規則的新群組，在第一則 message 前就能被設定成對應的 observer / safe profile。
- 第一則真正 user message 到來時，系統直接使用已套好的 route policy，不需要再靠 fallback bot 補救。

## Open Questions

- dynamic onboarding state 應存在哪一層：
  - in-memory only
  - persisted sidecar / JSON
  - 或 route metadata store
- discovery profile 是否應與後續 `/cli` 手動調整 route policy 共用同一份 runtime state 模型
- LINE room (`R...`) 是否正式納入 onboarding 保證範圍；目前可 discovery，但 label enrichment 與 pre-message guarantee 都弱於一般 group
- `label keyword match` 是否需要支援：
  - 任一 keyword match
  - 全部 match
  - regex
  這輪先不做過度設計
