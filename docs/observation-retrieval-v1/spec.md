# Observation Retrieval V1 Spec

## Summary

這輪要把 observer 的查詢能力，從目前的：

- `group`
- `category`
- `days`
- exact-ish DB lookup

提升成 **DB-first、自然語言驅動、可控的 observation retrieval**。

核心不是做 RAG，而是：

- `route_group` 只管可見性 / 查詢範圍
- 每個 source `route_id` 用自己的 `observation_profile` 定義收集與查詢方法
- tool 先做 **query-aware top-k candidate shortlist**
- chatbot session 的 LLM 再決定真的查哪幾個 source members
- 每個 source 各自查、各自回
- 最終要不要 merge，交給 LLM

## Problem

目前 observer query 有三個明顯缺口：

1. `observation_profile.instructions` 沒真的進 observer worker prompt
   - profile 名稱有了
   - `batch_size` / `categories` 有用
   - 但真正的整理意圖沒有進 session

2. `query_observations(group=...)` 的 retrieval surface 太硬
   - 偏 exact category / days 過濾
   - 不夠自然語言
   - LLM 難以靠一般問句穩定命中正確來源

3. group 與 method 的責任容易混掉
   - `route_group` 其實管的是：
     - 誰可以看到哪些知識
   - 不是：
     - 該怎麼存
     - 該怎麼查

## Goals

- 讓 `observation_profile.instructions` 正式進 observer worker prompt
- 建立 DB-first 的 retrieval path，不做 vector RAG
- 明確定義：
  - `route_group`
  - `observation_profile`
  - source `route_id`
  在 retrieval 的責任切分
- 讓 chatbot 可以用自然語言問題，先拿到 query-aware candidate shortlist
- 讓 LLM 自己決定要查哪些 source members
- 每個 source route 可以用自己的 retrieval method
- 結果預設以 **per-source array** 回傳，不強制先做 merge

## Non-Goals

這輪不做：

- vector/embedding RAG
- cross-source hard merge engine
- runtime 自動改 schema
- 讓 agent 直接改 `observation_entries` schema
- 一次解完整的 admin / capabilities 問題

## Core Decisions

### 1. `route_group` 只管 access / query scope

`route_group` 的責任是：

- 定義哪一些 source routes 在同一個可見知識池
- 定義哪一些 consumer routes 可以查這一池知識

`route_group` **不管**：

- capture 方法
- semantic 方法
- entry projection 方法

它回答的是：

> 誰看得到哪些知識

### 2. `observation_profile` 管 capture 方法與 retrieval 方法

每個 source `route_id` 透過 `binding.observation.capture.profile` 指向自己的 `observation_profile`。

這個 profile 決定：

- observer worker prompt 應該怎麼整理資料
- 允許哪些 categories
- 要投影出什麼 retrieval-friendly entries
- 適合回答什麼類型的 query

所以：

- 同一個 `route_group` 內可以混用不同 profile
- method 不在 group，而在 source route/profile

### 3. observer worker prompt 必須吃到 `profile.instructions`

這輪定案：

- `observation_profile.instructions` 必須正式進 observer worker prompt
- `categories` 與 `instructions` 共同構成 capture contract
- `mode` 若暫時未實作完整 runtime semantics，也至少不能阻止 `instructions` 生效

也就是說，當 source route 設定：

```yaml
observation:
  capture:
    group: shinyipaint_ops
    profile: warehouse_ops
```

那 `warehouse_ops.instructions` 必須真的進 observation worker session。

### 4. 保留 `memory_observations`，新增 `observation_entries` 作為 retrieval projection

資料分兩層：

#### `memory_observations`

- 仍作為 observer batch 的 canonical persisted result
- 保留原始 batch summary / batch JSON

#### `observation_entries`

- retrieval projection
- 給自然語言查詢與 per-profile retrieval adapter 用
- 可存兩種 row：
  - `fact`
  - `semantic`

`semantic` row 只作為 retrieval aid，不可創造新事實。

### 5. group query 不必全查，也不必先 merge

`route_group` 底下有 N 個 source routes，不代表每次都要：

- 全部查
- 先 merge 完再回

這輪定案：

- 先做 **candidate selection**
- 只查值得查的 top-k members
- 每個 member 各自查、各自回
- 最終回答的 merge / synthesize 交給 LLM

### 6. candidate selection 是 query-aware top-k shortlist

這輪不做 vector score。

這輪做的是：

- config-aware
- fuzzy / heuristic
- top-k candidate shortlist

用來決定：

> 在這個 group 的所有 source members 裡，哪些值得先查

### 7. candidate selection 由 tool 做 shortlist，LLM 做最終決策

這輪不讓 tool 直接替 LLM 決定要查誰。

流程是：

1. tool 根據 query 與 profile metadata 產生 shortlist
2. LLM 看 shortlist
3. LLM 決定真的要查哪幾個 members
4. 再逐一呼叫 per-member query tool

這樣：

- selection 的前半可控
- 最後的查詢策略仍交給 LLM

### 8. top-k scoring 先採 heuristic relevance score

V1 的 candidate score 來自：

- `profile.retrieval.keywords`
- `profile.retrieval.description`
- `profile.categories`
- route label
- query tokens

先不做 embeddings。

### 9. `observation_profile` 需要新增 `retrieval` metadata

V1 在 profile 補：

```yaml
observation_profiles:
  warehouse_ops:
    instructions: |
      持續整理群組中的營運脈絡。
      忽略純閒聊，保留可回查、可彙總、可同步的背景知識。
    categories: [請假, 進料, 出料, 出貨, 工程進度, 客訴, 行程, 庫存, 其他]
    retrieval:
      description: >
        適合回答請假、進出料、出貨、工程進度、庫存與一般營運脈絡查詢。
      keywords: [請假, 休假, 進料, 出貨, 庫存, 物料, 工程]
```

這些 metadata 不直接回答問題，  
而是用來做 candidate shortlist。

## Data Model

### `observation_entries`

V1 最小欄位：

- `id`
- `route_id`
- `group`
- `profile_name`
- `kind`
  - `fact`
  - `semantic`
- `canonical_entry_id`
  - `fact` 可為空
  - `semantic` 指向對應 `fact`
- `category`
- `who`
- `record_date`
- `content`
- `search_text`
- `facets_json`
- `source_observation_id`
- `created_at`

### `kind=fact`

- 直接來自 observer batch 整理出的事實條目
- 應能追溯到 `memory_observations`

### `kind=semantic`

- 只用於提升查詢 hit rate
- 可補：
  - alias
  - synonym
  - search-friendly paraphrase
  - intent hint
- **不得創造新事實**

## Tool Surface

### 1. `list_observation_candidates`

輸入：

- `group`
- `query`
- optional `top_k`

輸出：

```json
[
  {
    "route_id": "line:shinyipaint:C006...",
    "label": "倉庫群",
    "profile": "warehouse_ops",
    "profile_description": "適合回答請假、進出料、出貨、工程進度、庫存與一般營運脈絡查詢。",
    "categories": ["請假", "進料", "出料", "出貨", "工程進度", "客訴", "行程", "庫存", "其他"],
    "reason": "query 與請假/營運類別高度相關",
    "score": 11,
    "suggested_priority": 1
  }
]
```

用途：

- 給 LLM 看 query-aware shortlist
- 不是直接回最終答案

### 2. `query_observation_member`

輸入：

- `route_id`
- `query`
- optional `days`
- optional `limit`

輸出：

```json
{
  "route_id": "line:shinyipaint:C006...",
  "profile": "warehouse_ops",
  "entries": [
    {
      "category": "請假",
      "who": "阿明",
      "record_date": "2026-04-08",
      "content": "明天下午請假",
      "evidence_ref": "obs_123"
    }
  ]
}
```

用途：

- 針對單一 source member 做 profile-owned retrieval

### 3. `query_observations`

保留作為既有 exact/group 查詢工具，供相容性或內部橋接使用。  
但對 chatbot 的主查詢路徑，V1 以：

- `list_observation_candidates`
- `query_observation_member`

為主。

## Candidate Scoring

V1 先採明確、可 debug 的 heuristic score。

### Query normalization

先做：

- lowercasing（若語言適用）
- punctuation stripping
- tokenization
- category alias normalization

### 每個 candidate 的 score 組成

對 group 內每個 source route：

1. category hit
   - query token 命中 profile `categories`
   - `+4`
2. retrieval keyword hit
   - query token 命中 `retrieval.keywords`
   - `+3`
3. profile description overlap
   - query token 與 `retrieval.description` 有明顯重疊
   - `+2`
4. route label hit
   - query token 命中 route label
   - `+1`
5. exact route label phrase hit
   - query 直接提到 route label phrase
   - `+2`

### shortlist 規則

- 預設 `top_k = 3`
- 最大 `top_k = 5`
- score `<= 0` 的 candidate 不進 shortlist
- 若全部 score `<= 0`
  - 回傳空 shortlist
  - 由 LLM 決定是否改問法或走 fallback tool path

## Dataflow

### Capture dataflow

1. source route message 進 observation lane
2. 達 batch size
3. observer worker session 啟動
4. worker prompt 組成：
   - base observer system prompt
   - `observation_profile.instructions`
   - categories hint
5. worker 輸出 batch JSON
6. 寫入 `memory_observations`
7. 同步投影 `observation_entries`

### Query dataflow

1. consumer route 問自然語言問題
2. chatbot session 判斷需要 group knowledge
3. tool call:
   - `list_observation_candidates(group, query, top_k)`
4. tool 根據 group members + profile retrieval metadata 算 shortlist
5. LLM 看 shortlist，決定查 1~N 個 members
6. tool call:
   - `query_observation_member(route_id, query, ...)`
7. 各 member 依自己的 profile 方法查 `observation_entries`
8. 每個 member 各回一包結果
9. LLM 自己 synthesize 最終答案

## Tool Call Stack

### Example

使用者在 admin/private route 問：

> 請問最近誰請假？

預期 stack：

1. chatbot session 呼叫：
   - `list_observation_candidates(group="shinyipaint_ops", query="請問最近誰請假？")`
2. tool 回 shortlist：
   - 倉庫群 / 請假登記群 / 其他
3. chatbot session 根據 shortlist 呼叫：
   - `query_observation_member(route_id="line:shinyipaint:C006...", query="請問最近誰請假？")`
   - 若需要再呼叫第二個 member
4. tool 各回 per-member entries
5. chatbot session 自己整理成最終回答

這輪**不要求** tool 在第 4 步之後先做 cross-source merge。

## Open Constraints

- `observation_profile.instructions` 必須正式接進 capture worker prompt，否則 profile 仍是半套
- `query_observation_member` 的 per-profile retrieval adapter 必須有統一輸出 shape
- `observation_entries` 的 `semantic` row 只能做 retrieval aid，不得創造新事實

## Success Criteria

- `warehouse_ops.instructions` 之類的 profile instructions 真正進 observer worker prompt
- 自然語言 query 不需要先精準知道 category 名稱，也能 shortlist 到對的 source members
- 不同 profile 的 source routes 可以共存在同一 `route_group`
- chatbot 可以先拿 shortlist，再決定查哪些 members
- 結果預設以 per-source array 回傳，LLM 可直接做 final synthesis
