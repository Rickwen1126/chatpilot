# Observation Retrieval V1 Plan

## Status

Planned on 2026-04-07.

這輪先落 spec / plan，不直接擴成 RAG 或 merge engine。

## Goal

在現有 observer 架構上補齊：

- capture prompt 真正吃到 `observation_profile.instructions`
- DB-first retrieval projection
- query-aware top-k candidate selection
- LLM 主導的 member query stack

讓自然語言查詢可以：

1. 先拿 candidate shortlist
2. 再決定查哪些 source members
3. 最後自己整理答案

## Scope

### In scope

- `observation_profile.instructions` prompt wiring
- `observation_profile.retrieval` metadata
- `observation_entries` projection
- `list_observation_candidates`
- `query_observation_member`
- chatbot 對這兩個 tools 的使用引導

### Out of scope

- vector / embedding retrieval
- 強制 cross-source merge
- runtime schema mutation
- capabilities / admin control plane

## Design Principles

### 1. group 只管 access scope

`route_group` 只決定：

- 這條 consumer route 可以看哪些 source routes

### 2. method 回到 source route/profile

每個 source route 用自己的 `observation_profile`：

- capture
- retrieval
- semantic entrance

### 3. tool 做 shortlist，不替 LLM 做最後決策

tool 先把可能有答案的來源排出來，  
真正查哪幾個 members，由 chatbot session 的 LLM 決定。

### 4. 不先做 merge engine

V1 預設回 per-source result array，  
merge / synthesis 交給 LLM。

## Implementation Strategy

### Phase 1 — Profile Retrieval Metadata + Prompt Wiring

#### 目標

- `observation_profile.instructions` 真正進 observer worker prompt
- profile 補 `retrieval` 區塊

#### config shape

```yaml
observation_profiles:
  warehouse_ops:
    mode: batch
    batch_size: 10
    instructions: |
      持續整理群組中的營運脈絡。
      忽略純閒聊，保留可回查、可彙總、可同步的背景知識。
    categories: [請假, 進料, 出料, 出貨, 工程進度, 客訴, 行程, 庫存, 其他]
    retrieval:
      description: >
        適合回答請假、進出料、出貨、工程進度、庫存與一般營運脈絡查詢。
      keywords: [請假, 休假, 進料, 出貨, 庫存, 物料, 工程]
```

#### code path

- observer worker prompt builder
- `ObservationProfileConfig` schema
- config validation

### Phase 2 — `observation_entries` Projection

#### 目標

- 在保留 `memory_observations` 的前提下，新增 retrieval projection

#### 新增 table

建議新增 `observation_entries`：

- `id`
- `route_id`
- `group`
- `profile_name`
- `kind`
- `canonical_entry_id`
- `category`
- `who`
- `record_date`
- `content`
- `search_text`
- `facets_json`
- `source_observation_id`
- `created_at`

#### capture dataflow

1. source route message 進 observation lane
2. 達 batch size
3. worker prompt 帶入：
   - base system prompt
   - `profile.instructions`
   - categories hint
4. worker 回傳 batch JSON
5. 寫 `memory_observations`
6. 同步投影 `observation_entries`

### Phase 3 — Candidate Shortlist Tool

#### 新增 tool

`list_observation_candidates(group, query, top_k=3)`

#### 候選來源

從 `group` 展開所有 source routes，  
每個 source route 取：

- route label
- `profile_name`
- `profile.retrieval.description`
- `profile.retrieval.keywords`
- `profile.categories`

#### score 規則

每個 source route 的 score：

1. category hit
   - `+4`
2. retrieval keyword hit
   - `+3`
3. description overlap
   - `+2`
4. route label hit
   - `+1`
5. exact route label phrase hit
   - `+2`

#### shortlist 規則

- default `top_k = 3`
- max `top_k = 5`
- score `<= 0` 不入列
- 按 score descending 輸出

#### output shape

```json
[
  {
    "route_id": "line:shinyipaint:C006...",
    "label": "倉庫群",
    "profile": "warehouse_ops",
    "profile_description": "...",
    "categories": ["請假", "進料", "出貨"],
    "reason": "query 與請假/營運類別高度相關",
    "score": 11,
    "suggested_priority": 1
  }
]
```

### Phase 4 — Per-Member Query Tool

#### 新增 tool

`query_observation_member(route_id, query, days?, limit?)`

#### 核心責任

- 接單一 source route
- 找到這個 route 對應的 `observation_profile`
- 依 profile 方法查 `observation_entries`
- 回傳 per-source entries

#### V1 retrieval strategy

先不做不同 profile 的獨立 code plugin system。  
V1 可先：

- 共用一套 DB query skeleton
- 但依 profile metadata 做不同條件過濾 / ranking

後續若 profile 差異變大，再抽 retrieval adapter interface。

### Phase 5 — Chatbot Prompt + Tool Guidance

#### 目標

讓 chatbot 知道：

- group query 不必全查
- 先 shortlist
- 再自己決定查哪些 members

#### prompt guidance

當 route 有 `observation.consume` 時，注入：

- 可 consume 的 `group -> description`
- 使用原則：
  - 先用 `list_observation_candidates`
  - 再選擇 1~N 個值得查的 members
  - 不要預設 group 全查

## Dataflow

### Query dataflow（canonical）

1. 使用者在 consumer route 問自然語言問題
2. chatbot session 判斷需要 group knowledge
3. tool call：
   - `list_observation_candidates(group, query, top_k)`
4. tool 展開該 group 的 source routes
5. 依 profile retrieval metadata 算 score
6. tool 回 shortlist
7. chatbot session 根據 shortlist 決定查 1~N 個 members
8. tool call：
   - `query_observation_member(route_id, query, ...)`
9. 各 member 回 per-source entries
10. chatbot session 自己 synthesize 最終回答

## Tool Call Stack

### Example 1 — 請假查詢

使用者：

> 最近誰請假？

預期 stack：

1. `list_observation_candidates(group="shinyipaint_ops", query="最近誰請假？", top_k=3)`
2. chatbot session 收到 shortlist
3. 先查：
   - `query_observation_member(route_id="line:shinyipaint:C006...", query="最近誰請假？")`
4. 若結果不夠，再查第二個 member
5. LLM 自己整理答案

### Example 2 — 庫存查詢

使用者：

> 最近底漆庫存怎麼樣？

預期 stack：

1. `list_observation_candidates(group="shinyipaint_ops", query="最近底漆庫存怎麼樣？", top_k=3)`
2. shortlist 應優先推：
   - `warehouse_ops` 類型來源
3. chatbot session 只查最相關的 1~2 個 members
4. 不要求 group 全查

## Validation Plan

### Unit

- `observation_profile.instructions` 真正進 observer prompt builder
- `retrieval.description/keywords` schema validation 正確
- candidate scoring 對 category / keyword / label 的加權正確
- `top_k` / score threshold 正確
- `query_observation_member` 能依 route 找到正確 profile

### Integration

- observer capture 後，`memory_observations` 與 `observation_entries` 皆正確寫入
- `list_observation_candidates` 能依 query 回正確 shortlist
- `query_observation_member` 能回對應 route/profile 的 entries
- chatbot prompt 看到可 consume group description 與 tool guidance

### E2E

至少補一條新 feature E2E，做到 L3：

1. 建 source routes，讓不同 profile 寫入 observation data
2. consumer route 問自然語言問題
3. 驗 log：
   - `list_observation_candidates` 被呼叫
   - `query_observation_member` 被呼叫
4. 驗 DB：
   - `observation_entries` 有正確投影
5. 驗最終回答：
   - 能從正確 source 拿到答案

關鍵 query 再補一條 L4：

- 驗「不需要 group 全查，仍能命中正確 member」

## Risks

### 1. heuristic score 太弱

若 `retrieval.description/keywords` 不夠好，shortlist 可能不準。

對策：

- V1 先明確人工配置 retrieval metadata
- miss cases 再回補 metadata

### 2. `semantic` rows 汙染事實層

若 semantic row 開始創造新事實，retrieval 可信度會崩。

對策：

- spec 明確禁止 semantic row 創造新事實
- `canonical_entry_id` 必須可追溯到 fact row

### 3. tool over-selection

若 chatbot session 每次都查很多 members，成本會升高。

對策：

- prompt 明寫：先查最相關的 1~2 個
- shortlist default `top_k = 3`
- 不鼓勵全查

## Deliverable

這輪完成後，應得到：

- observation capture 真的尊重 `observation_profile.instructions`
- `observation_entries` projection
- query-aware top-k shortlist tool
- per-member query tool
- 明確的 chatbot tool call stack
- 不做 RAG，也能自然語言查 group knowledge 的 V1 路徑
