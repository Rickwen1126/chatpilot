# FileHandleCenter 設計定調

## 結論

目前 file/media 這條線的設計定調如下：

- `adapter` 負責平台翻譯與平台抓取能力
- 系統流程內只傳遞單一 canonical file handle，不再暴露平台原生 file 規則
- `FileHandleCenter` 是系統內的 file handling service，不是另一個平台 adapter
- `FileHandleCenter` 負責：
  - canonicalization
  - `file_id` 分配
  - eager / lazy policy
  - download / prefetch orchestration
  - local materialization
  - 後續 scan / TTL / storage lifecycle
- `tool` / `agent` 不直接處理平台差異，只消費被允許的 file result

這條設計沿用現有 message adapter / hub 的 pattern：

- 平台差異留在 adapter edge
- 系統內只看統一契約
- orchestration 交給中心服務

## 核心分層

### 1. Adapter

adapter 是平台邊界。

它的責任是：

- 把平台原生 file/media event 翻成系統可理解的 source handle input
- 根據 source handle input 回平台抓取原始檔案 bytes

它**不**負責：

- 分配 `file_id`
- 決定 eager / lazy download
- 決定 sync / async orchestration
- 落地 local path
- asset TTL / scan / storage policy

### 2. FileHandleCenter

`FileHandleCenter` 是系統內的 file handling boundary。

它的責任是：

- 接收 adapter 翻譯出的 source handle input
- 建立 canonical file record
- 分配 opaque `file_id`
- 根據 policy 決定：
  - 只 register
  - 立即 blocking download
  - background prefetch
- 管理 local materialization / scan / TTL / 後續 storage lifecycle

它**不**應該知道：

- LINE / Telegram / Discord 原生 webhook payload 長什麼樣
- 各平台下載 URL 怎麼拼
- 各平台的 attachment native rule

### 3. Tool / Agent

tool 與 agent 只看系統內 canonical file identity 與後處理結果。

它們不應該：

- 自己 parse 平台 ref grammar
- 直接碰 adapter-specific file payload
- 自己決定怎麼從平台抓檔

agent 對檔案的能力應由 tool 決定，而不是由 `FileHandleCenter` 直接暴露。

## Canonical File Handle

### 基本原則

- `CanonicalFileHandle` 代表的是 **source identity**
- 它不是 local file path
- 它不是 uploaded asset URL
- 它不是 scan result
- 它不是 materialized asset

### 主鍵策略

- `file_id` 使用 opaque UUID
- `file_id` 是系統內真正的 primary key
- `file_id` 由 `FileHandleCenter.register(...)` 分配
- adapter 不分配 `file_id`

這個決策是刻意避免把 source fields 直接長成真正 primary key。

### 建議欄位

目前已定調的欄位方向：

- `file_id`
- `route_id`
- `platform`
- `native_locator`
- `kind`
- `filename?`
- `mime_type?`
- `platform_context`

欄位語意：

- `route_id`
  - 檔案所屬的 target route
  - 是一等公民，但屬於 ownership / partition，不是 source identity 本體
- `platform`
  - 用來 resolve 對應 adapter
- `native_locator`
  - adapter 回平台抓檔需要的原生定位資訊
  - 不保證只是單一 message id
- `filename` / `mime_type`
  - descriptor，不作為 primary key
- `platform_context`
  - 只保留 adapter fetch 真正需要、無法自然放進通用欄位的資訊

## Source Handle 與 Materialized Asset 分離

這次討論已明確定調：

- `SourceHandle` / `CanonicalFileHandle`
  - 表示來源身份
- `MaterializedAsset`
  - 表示已下載 / 已落地 / 已上傳的資產狀態

不要把這兩者混成同一個概念。

特別是：

- 不要把 source `platform` 直接改寫成 `local`
- `local` 應被視為 materialization backend，而不是 source platform

## Sync / Async 的責任線

sync / async 不是 adapter 的平台責任，而是 `FileHandleCenter` 的 orchestration 責任。

換句話說：

- adapter 提供單一 fetch primitive
- `FileHandleCenter` 決定要 blocking 下載還是 background prefetch

這樣平台能力與使用模式才不會綁死。

### 命名偏好

概念上可以說是 file materialization，但 API 命名可偏直覺：

- `register`
- `download_now`
- `prefetch`
- `ensure_local`

文件裡可以繼續使用 materialization 描述概念，
但對外 method name 優先採用較直覺的詞彙。

## Ingress Policy

預下載不應由 adapter 自己開 side path 去呼叫 `FileHandleCenter`。

正確流程應該是：

1. adapter 先翻譯出 source handle input
2. 主流程中的 ingress preprocessing step 呼叫 `FileHandleCenter.register(...)`
3. `FileHandleCenter` 依 policy 決定 eager / lazy / background
4. message 再繼續進 hub / chatbot / pipeline

這樣可以同時成立：

- adapter 責任不膨脹
- `file_id` 由中心分配
- 預下載可在 ingress 時發生
- 不會長出 adapter side-channel

## Policy 定位

policy 是這條設計的重要伸縮點。

它可以依據不同訊號決定是否 eager download：

- file `kind`
- `platform`
- `route_id`
- message context
- feature flags
- pipeline / tool demand

關鍵原則是：

- policy 可以一直變
- 但 `adapter`、`register`、主流程不因此改形

## Storage 與 DB 原則

目前已達成的高層決策：

- route-scoped file asset 需要固定 storage layout
- 需要 files index DB
- 需要 retention / cleanup policy
- local-first desktop deployment 下，SQLite 是合理選擇

這些細節仍待進一步拍板，但方向已確定。

## 一句話原則

**adapter 負責翻譯平台差異，FileHandleCenter 負責系統內 file orchestration；流程內只傳遞 canonical file handle，預下載與背景下載一律由 register 後的 policy 決定。**
