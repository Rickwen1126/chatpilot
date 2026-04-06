# Observer VNext Plan

## Scope

本輪只做 observer core replacement：

- 以 `route_group` 取代舊 observer source label 概念
- 以 `binding.reply_policy` + `binding.observation` 取代舊 `chatbot.observer_mode`
- `query_observations` 直接改成以 `group` 為 canonical API
- 保持 observation 持久化仍為 route-local storage

這輪不做：

- `follow/join` discovery onboarding
- `smart` reply policy
- event schema 細化
- bot-level persistent memory
- file/STT/recent recall 類行為修正

## Design Constraints

- `route_id` 仍是 storage unit；不新增 bot-level memory table
- `route_group` 是 sharing/query unit；是正式 config，但不含 `members`
- membership 只能從 `binding.observation` 推導，不能雙重維護
- `reply_policy` 本輪只支援：
  - `silent`
  - `addressed`
- `addressed` 的判定語意沿用現有 adapter/hub addressed 規則：
  - private/direct route：通常每句都 addressed
  - group/shared route：mention / keyword / slash / 平台規則命中才 addressed
- 不保留舊 observer config 並存；新 schema 一次替換
- `route_group` 這輪保持薄，但實作不得把其結構寫死成只有 `description`
- 互動回話與 observation summarize 必須是兩條分離 execution lane：
  - chatbot reply 走互動 session
  - observation capture/batch summarize 走獨立 worker session
  - 不可共用同一 session context
- Message Hub 只保有一份 canonical inbound message，但必須 fan-out 成不同 lane：
  - reply intent
  - observation intent
- observation intent 不可直接共用現有 `ContextBuffer`
  - 必須有獨立 observation buffer / capture queue

## Implementation Plan

### Phase 1. Config Schema Replacement

目標：讓 config 正式表達 observer vNext，不再依賴舊欄位。

要做：

- 在 config model 中新增：
  - `route_groups`
  - `observation_profiles`
  - `bindings[].reply_policy`
  - `bindings[].observation.capture`
  - `bindings[].observation.consume`
- 移除舊 observer config 入口：
  - `chatbot.observer_mode`
  - `observer_batch_size`
  - `observer_categories`
  - `observer_allowed_consumers`
- 補 schema validation：
  - `route_group` 不接受 `members`
  - `capture` 僅允許單一 `group + profile`
  - `consume` 是 group name list
  - `reply_policy` 僅允許 `silent | addressed`

完成條件：

- 新 config 能 parse
- 舊 observer config 會明確 fail fast，而不是靜默 fallback

### Phase 2. Runtime Wiring Rewrite

目標：observer 註冊與查詢路徑改由 binding policy 驅動。

要做：

- server startup / reload 時：
  - 不再從 chatbot config 掃 `observer_mode`
  - 改為從 binding 掃 `reply_policy` + `observation`
- runtime 建立 group membership 視圖：
  - source routes：來自 `capture.group`
  - consumer routes：來自 `consume[]`
- 保留 route-local observation storage：
  - batch summarize 仍存到 `memory_observations.route_id`
- 建立 observation buffer / capture queue：
  - 由 Hub fan-out 進 observation lane
  - 不與互動 `ContextBuffer` 共用 state
- 建立 observation worker path：
  - 由 profile 啟動獨立 summarize session
  - 不復用互動 chatbot session
- 移除舊 observer source map / chatbot name fallback

完成條件：

- observer source 與 consumer 都可由 binding 正確推導
- runtime 不再依賴 `chatbot_name` 作為 query identity

### Phase 3. Hub Behavior Replacement

目標：把 observer 行為明確對齊到 `reply_policy + observation`。

要做：

- hub `receive()`：
  - 先建立 canonical inbound message
  - 先套 binding
  - 依 `reply_policy` 決定是否可回話
  - 依 `observation.capture` 決定是否做 capture
- 當同一路 route 同時有 `addressed` 回話與 `capture`：
  - reply 與 summarize 可以由同一批 inbound message 觸發
  - 但必須先 fan-out 成不同 intent
  - 並走不同 buffer / session path
- `silent`：
  - 不進 chatbot reply path
  - 但仍可走 file/STT preprocessing，再進 capture
- `addressed`：
  - 只在 addressed 時進 chatbot
  - 非 addressed 訊息仍可 capture（若 binding 有設定）
- `send_reply()` / `push()` / pipeline return path：
  - 仍需防守 `silent` route 不回話

完成條件：

- `silent` / `addressed` 的 runtime 行為與 spec 一致
- observer 群組靜默防線仍成立

### Phase 4. Query API Cutover

目標：`query_observations` 直接變成 group-based。

要做：

- tool input 改為 `group`
- runtime：
  - `group -> source routes -> memory_observations(route_id=...)`
- 權限檢查改成：
  - caller route 是否在該 group 的 consumer routes 中
- 移除：
  - source label
  - chatbot-name-derived source identity

完成條件：

- `query_observations(group=...)` 是唯一 canonical path
- 既有 observer query 行為在新抽象下仍可達成

### Phase 5. Config Migration In-Repo

目標：把 repo 內正式 config 切成新 observer schema。

要做：

- 更新 `config/routes.yaml`
- 更新 `config/routes.example.yaml`
- 若 README / docs 有舊 observer config 範例，一併更新
- 把目前 observer 相關 production-like 配置映射成：
  - `route_groups`
  - `observation_profiles`
  - `binding.reply_policy`
  - `binding.observation`

完成條件：

- repo 不再留 active 舊 observer config 作為正式做法

## Validation Strategy

### Unit

- config parser / validation：
  - 新 schema parse 正確
  - 舊 observer config fail fast
  - `route_group` 拒收 `members`
- runtime membership：
  - source routes 推導正確
  - consumer routes 推導正確
- buffer boundary：
  - observation capture 不共用互動 `ContextBuffer`
  - 同一 inbound message 可 fan-out 成兩個 intent
- session boundary：
  - observation summarize 走 worker session
  - reply path 不復用 summarize session
- `addressed` 語意：
  - private route 視為 addressed
  - group route 依現有 mention/keyword/slash 判定
- `query_observations(group=...)`：
  - group 可展開正確 route set
  - 非 consumer route 會被拒絕

### Integration / Self-contained E2E

至少補這三組：

1. `silent + capture`
   - 不回話
   - 仍會寫 observation row
   - DB 有 route-local observation

2. `addressed + capture`
   - private route：一般訊息可回
   - group route：只有 addressed 訊息可回
   - 非 addressed 訊息若有 capture 仍會寫 observation
   - reply 與 summarize log 可分別證明是不同 buffer / session path

3. `consume -> group query`
   - source route 先寫 observation
   - consumer route 可查到
   - 非 consumer route 查不到

### Live Verification

merge 前至少再做一輪最小 live check：

- observer 群組：
  - `silent` 不回話
  - image/audio/file 仍可 capture
- consumer route：
  - addressed 問 observation 問題時會走 `query_observations(group=...)`

## Risk Notes

- 這輪不保留舊 config，代表 config migration 要一次到位
- `addressed` 是跨平台抽象，若 adapter/hub 規則不一致，行為可能漂
- 若在本輪把 `route_group` 擴成 ACL/onboarding/sync 中樞，scope 會失控

## Suggested Execution Order

1. config schema / validation
2. runtime membership view
3. hub behavior replacement
4. `query_observations` cutover
5. repo config migration
6. unit / self-contained E2E
7. live check
8. codetour + review

## Milestone Definition

這輪 milestone 完成條件：

- repo 內不再使用舊 observer config
- observer source/query identity 不再依賴 chatbot name 或 source label
- `silent | addressed` 行為已被 unit + E2E 證明
- `query_observations(group=...)` 已在新抽象下運作
