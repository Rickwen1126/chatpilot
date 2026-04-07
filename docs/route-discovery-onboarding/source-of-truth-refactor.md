# Route Discovery Onboarding Source-of-Truth Refactor

## Summary

這份小 spec+plan 用來修正目前 discovery onboarding 的核心抽象錯誤。

目前最大的問題不是 `follow/join` webhook 或 profile matching，而是：

- discovery 結果被寫進 `RouteOnboardingRegistry`
- runtime routing 又另外看 static bindings / Hub policy
- 導致 route discovery 後，實際生效的設定不是單一來源

本次修正的目標很單純：

**discovery 完成後，直接把結果落成系統真正使用的 route binding。**

## Problem

目前 route 行為資訊分散在：

1. static bindings
2. `RouteOnboardingRegistry`
3. `hub._route_policies`

其中只有第 1 和第 3 應該存在於同一條來源鏈上：

- static bindings / route bindings 是 canonical config source
- `hub._route_policies` 只是 runtime projection / cache

`RouteOnboardingRegistry` 這個中介層不應該存在，因為它造成：

- discovery onboarding 走成平行支線
- restart 後 route 還在，但 onboarding policy 會掉
- `/cli/routes` 必須拼裝不同來源的 state
- source of truth 不單一，debug 與 reload 語意都不清楚

## Core Decision

### 1. Binding 單一來源

之後 binding 的唯一來源是一個檔案：

- `config/route_bindings.yaml`

不再分：

- static bindings 一份
- discovered bindings 一份

也不再把 discovery 結果寫進獨立 registry。

### 2. `routes.yaml` 改名為 `route_settings.yaml`

原本的 `config/routes.yaml`（legacy）應改名為：

- `config/route_settings.yaml`

它只保留：

- `chatbots`
- `route_groups`
- `observation_profiles`
- `discovery_profiles`
- `discovery_rules`
- adapter / scheduler / 其他非 binding 設定

也就是：

**人類維護規則與設定**

不再承載 route binding 本身。

### 3. Discovery 直接 materialize 成 binding

`follow/join` discovery 發生時：

1. 依 `discovery_rules + discovery_profiles` 選 profile
2. 生成這條 `route_id` 的 exact route binding
3. 寫入 `config/route_bindings.yaml`
4. 同步更新記憶體中的 routing state
5. 同步 rehydrate Hub policy cache

所以 discovery 不再是平行 runtime state，
而是 **route binding 的初始化器**。

### 4. `hub._route_policies` 保留，但降回純快取

`hub._route_policies` 不需要拔掉，但它只能：

- 從 `route_bindings.yaml` 載入後派生
- 作為 `receive()` 的快速 gate cache

它不再是第二份真相。

### 5. 寫檔後即時生效，不靠 reload

discovery / admin 對 route binding 的變更：

- 寫 `route_bindings.yaml`
- 同步更新 in-memory binding state
- 同步刷新 Hub policy

所以：

- discovery 後不需要再做 reload 才生效
- 第一則真正 message 就應該直接走新 binding

`/cli/reload` 的用途只剩：

- 人手改了 `route_settings.yaml`
- 或人手改了 `route_bindings.yaml`
- 需要重新讀 disk config

### 6. 最小改動原則

這次 refactor 不追求重做整個 routing subsystem。

原則是：

- 保留既有 load/resolve 大方向
- 保留 `BindingRouter`
- 保留 `hub._route_policies`
- 改正 source of truth
- 移除 `RouteOnboardingRegistry`

也就是：

**修正資料來源，不擴大行為表面。**

## File-Level Plan

### Rename / Split Config

- `config/routes.yaml`（legacy）→ `config/route_settings.yaml`
- 新增 `config/route_bindings.yaml`

### `config/route_settings.yaml`

保留：

- adapters
- match_weights
- route_groups
- observation_profiles
- discovery_profiles
- discovery_rules
- chatbots
- scheduler / cron_scheduler / 其他設定

移除：

- `bindings`

### `config/route_bindings.yaml`

承接所有 binding。

建議結構：

```yaml
route_bindings_manual:
  line:shinyipaint:Ceead1a4ba637518e00059ac73ba2cd8a:
    match:
      platform: line:shinyipaint
      group_id: Ceead1a4ba637518e00059ac73ba2cd8a
    chatbot: shinyipaint
    reply_policy: addressed
    processing_policy: interactive
    observation:
      consume: [shinyipaint_ops]
    source: manual

route_bindings_auto:
  line:shinyipaint:Cdog:
    match:
      platform: line:shinyipaint
      group_id: Cdog
    chatbot: shinyipaint
    reply_policy: addressed
    processing_policy: interactive
    source: discovered
    profile_name: shinyipaint_main_group

fallback_bindings:
  - match: { platform: "line:shinyipaint" }
    chatbot: buddy
  - chatbot: buddy
```

設計原則：

- exact route binding 用 `route_id` 當 key，方便 upsert
- `route_bindings_manual` 給人手寫與明確覆蓋
- `route_bindings_auto` 給 discovery / runtime 自動補齊
- `manual > auto > fallback`
- generic platform/default fallback 仍用 list

## Runtime Plan

### Load

server startup / reload 時：

1. 讀 `route_settings.yaml`
2. 讀 `route_bindings.yaml`
3. 合併成單一 binding source
4. 建立 `BindingRouter`
5. 由 binding source 派生 `hub._route_policies`

### Discovery

`follow/join` 進來時：

1. 算出 canonical `route_id`
2. label enrichment
3. 套用 discovery profile
4. materialize 成 exact route binding
5. upsert 到 `route_bindings.yaml`
6. 同步刷新 router / hub 的 in-memory state
7. 若寫入來自 server 自己，watcher 應跳過這次 self-write，不做第二次 full reload

### CLI

`/cli/routes` 改成只看：

- `route_bindings.yaml` 的 effective binding
- active session / labels 作為補充 runtime info

不再看：

- `RouteOnboardingRegistry`

## Scope of Code Change

### 必須改

- `config/route_settings.yaml`
- `config/route_bindings.yaml`
- config loader
- [router.py](/Users/rickwen/code/chatpilot/src/chatpilot/routing/router.py)
- [webhook.py](/Users/rickwen/code/chatpilot/src/chatpilot/server/webhook.py)
- [__init__.py](/Users/rickwen/code/chatpilot/src/chatpilot/server/__init__.py)
- discovery materialization path
- `/cli/routes`

### 必須刪

- `RouteOnboardingRegistry`
- 依賴 registry 的 replay / merge / debug logic

### 應保留

- `BindingRouter`
- `hub._route_policies`
- `discovery_profiles`
- `discovery_rules`
- `follow/join` parser 與 discovery control path

## Validation

### Unit / Integration

- discovery 後會在 `route_bindings.yaml` 產生 exact binding
- 新 binding 立即反映到 router / hub
- restart 後 route 仍沿用同一份 binding
- `/cli/routes` 顯示的 chatbot / reply / processing 與 binding 一致

### E2E

- `join` 後不發 message，也可從 `/cli/routes` 看到正確 binding
- discovery 後第一則 message 直接走 materialized binding，不走 fallback
- restart server 後，既有 discovered route 行為不變

## Non-Goals

這次不做：

- capability system
- system/admin broadcast
- `shadow` processing policy
- route binding 的完整人工編輯 UI

## Acceptance

若以下成立，就算完成：

1. `RouteOnboardingRegistry` 已移除
2. binding 單一來源為 `route_bindings.yaml`
3. `routes_settings.yaml` 不再含 `bindings`
4. discovery 完成後會直接產生正式 route binding
5. restart 後 discovered route 的行為不變
6. `hub._route_policies` 仍存在，但只是派生 cache
