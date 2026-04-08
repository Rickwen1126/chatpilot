# Route Discovery Onboarding Plan

- Created: 2026-04-07
- Last Updated: 2026-04-08
- Status: completed

## Status

Implemented on 2026-04-07.

Validation baseline:
- `uv run ruff check src/ tests/`
- `uv run pytest tests/` → `210 passed`
- `bash tests/e2e/run_e2e.sh` → `65 passed / 0 failed`

## Goal

把 LINE route discovery 從「收到第一則訊息才知道 route」改成：

- `follow` / `join` 當下就建立 canonical route
- 立刻做 label enrichment
- 立刻套用 discovery profile
- 第一則真正 message 來時，直接使用已 materialize 的 route onboarding state

這輪的重點是 **pre-message onboarding**，不是完整 admin UI 或進階權限系統。

## Implementation Strategy

### Phase 1 — Discovery Event Support

先讓 LINE adapter / parser 能辨識 discovery 類事件，而不是只吃 `MessageEvent`。

目標：
- parser 能處理：
  - `FollowEvent`
  - `JoinEvent`
- webhook handler 能把這些 event 分流到 discovery path
- discovery event 不進 Hub 的一般 `receive(message, adapter)` 對話流程

這一步只解決：
- bot 被加好友 / 拉進群組時，系統能先知道 route 存在

不在這一步做：
- profile matching
- runtime override
- session 建立

### Phase 2 — Dynamic Route Onboarding State

加入一層 route-level runtime state，用來承接 discovery 後的預設 route policy。

這層 state 至少要能保存：
- `route_id`
- `chatbot`
- `reply_policy`
- `processing_policy`
- `observation`
- `discovered_at`
- optional label metadata

這層 state 應：
- 與 static bindings 並存
- 在 route resolve 時優先被考慮
- 不要求立刻寫回 static `bindings`

這一步的目的：
- 讓 discovery profile 真正落成 route-level policy

### Phase 3 — Discovery Profiles + Rules

在 config 裡新增：
- `discovery_profiles`
- `discovery_rules`

並完成：
- schema validation
- precedence 規則
- route_type / platform / id / label keyword matching

推薦 precedence：
1. exact id
2. label keyword
3. channel default
4. global default

這一步結束後，系統就能在 `follow/join` 當下：
- 根據 route 已知資訊
- 套用對應 profile

### Phase 4 — Label Enrichment

在 discovery 當下就反查名稱資訊：

- `join`
  - `get_group_summary`
  - `get_group_member_count`
- `follow`
  - `get_profile`

這些 label 應：
- 可被 runtime onboarding rule 使用
- 可寫入既有 `data/route_labels.json`
- 可出現在 `/cli/routes`

### Phase 5 — Routing Integration

讓 `BindingRouter` 與 route resolution 能看懂：
- static `bindings`
- dynamic onboarding state

預期行為：
- 如果某條 route 已有 dynamic onboarding state
  - 第一次 `MessageEvent` 來時直接用那份 policy
- 若沒有 dynamic onboarding state
  - 才回到 static binding / fallback 行為

這步的關鍵是：
- route onboarding state 不只是 admin 可見
- 而是真的能影響 runtime routing

## Data Model Plan

### New Config Objects

新增：
- `DiscoveryProfileConfig`
- `DiscoveryRuleConfig`

掛在 `GatewayConfig`：
- `discovery_profiles`
- `discovery_rules`

### New Runtime State

新增一層 app/server runtime state，例如：
- `route_onboarding_state`

它的用途：
- 保存 discovery 後 materialized 的 route policy
- 供 routing / admin / 後續調整共用

這輪先接受：
- in-memory runtime state

未來若需要：
- 再擴到 sidecar / JSON / metadata store

### Reuse Existing Models Where Possible

profile materialization 後，盡量沿用既有型別：
- `Binding` 相容欄位
- `ObservationConfig`

避免再創一套新的 route policy schema。

## Runtime Flow Plan

### `follow`

1. LINE webhook 進來
2. named adapter 驗證成功
3. parser 產生 discovery event payload
4. 生成 canonical route：
   - `line:shinyipaint:U...`
5. 反查 display name
6. 根據 discovery rules 選 profile
7. materialize runtime onboarding state
8. 更新 label store
9. 結束，不進 chatbot reply flow

### `join`

1. LINE webhook 進來
2. named adapter 驗證成功
3. parser 產生 discovery event payload
4. 生成 canonical route：
   - `line:shinyipaint:C...`
5. 反查 group summary / member count
6. 根據 discovery rules 選 profile
7. materialize runtime onboarding state
8. 更新 label store
9. 結束，不進 chatbot reply flow

### 第一則 message

1. `MessageEvent` 正常進 Hub
2. route resolve 時先查 runtime onboarding state
3. 若有命中：
   - 直接採用該 route 的 `chatbot/reply/processing/observation`
4. 若無命中：
   - 回到 static bindings

## Reload Semantics

`/cli/reload` 對 discovery onboarding 採 **snapshot semantics**：

- reload 會讀新的 disk config
- 影響之後新發現的 routes
- 也會把既有記憶體 onboarding state 重新掛回 runtime
- 但**不會**對已 discovery route 重新套用新 profile

若未來需要：
- 依新 config 對既有 discovered routes 做 reconcile
- 或手動重套 profile

那應作為另一個顯式功能，不和 reload 混在一起。

## Safe Defaults

### New Group

預設：
- `reply_policy = never`
- `processing_policy = none`

理由：
- 避免新群組被 discovery message 綁架
- 避免 bot 在高風險環境先亂回

### New Private Route

預設：
- discovery event 本身不回話
- 可配置便宜的 interactive chatbot 作為第一則 message 的預設

理由：
- 私聊風險較低
- 但 discovery 階段仍不應主動發話

### Hard Fallback

即使 config 遺漏了 channel/global default，runtime 仍保留 hard fallback：

- new group → `never + none`
- new private route → `addressed + interactive`

chatbot 優先使用 `buddy`；若不存在，再退回第一個可用 chatbot。

## Validation Plan

### Unit

- parser 能正確辨識 `FollowEvent` / `JoinEvent`
- config schema 能驗證：
  - discovery profile
  - discovery rule
- label keyword precedence 正確
- runtime onboarding state materialization 正確
- route resolution 會優先吃 onboarding state

### Integration

- `follow` 能建立：
  - canonical route
  - label
  - runtime policy
- `join` 能建立：
  - canonical route
  - label
  - runtime policy
- 第一則 message 會沿用 onboarding state，不走 fallback

### E2E

先做 self-contained / mock 型 E2E：
- `join` / `follow` 不進一般 chatbot reply flow
- `/cli/routes` 能看到 discovery 出來的 route
- label enrichment 正確
- 第一則 message 命中 discovery profile

真 LINE discovery E2E 留下一輪，不當這輪 blocker。

## Risks

### 1. Dynamic onboarding state 與 static bindings precedence 混亂

需要在 routing 時寫死 precedence，不然 debug 會很痛。

### 2. Label keyword match 過度依賴名稱

名稱會變，因此：
- 它只適合 onboarding convenience
- 不適合高風險授權

### 3. Runtime state 只放記憶體

若 server 重啟，discovery route 可能要重新補回。

這輪先接受，因為目標是先把 path 打通。

### 4. LINE room (`R...`) 行為弱於一般 group

目前 room route 可被 discovery，但：
- label enrichment 較弱
- pre-message guarantee 也不如一般 group 明確

這輪先列已知限制，不把 room 拉進和 group 同等的 onboarding 保證。

## Out of Scope For This Round

- `memberJoined`
- admin UI
- persisted onboarding state
- keyword regex / advanced matching
- `shadow` mode
- group 記憶匯入本身

## Recommended Next Step

寫 `tasks.md`，依下列順序拆：

1. parser / webhook discovery path
2. config schema for profiles/rules
3. runtime onboarding state
4. routing integration
5. label enrichment
6. unit/integration/E2E validation
