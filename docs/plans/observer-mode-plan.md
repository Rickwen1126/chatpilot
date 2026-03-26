# Plan: Observer Mode + Cross-Chat Query

> **日期：** 2026-03-26
> **狀態：** Draft

## Context

信益有一個幾十人的公司大群組，裡面有請假通知、出貨通知、工程進度等資訊。
需求：bot 進去只觀察不發言，定期整理資訊存 DB，管理者可在其他 chat 查詢。

## 設計原則

- Observer 是 chatbot 的 mode 設定，不是新元件類型
- 所有 chatbot 都有潛在 observer 能力，config 控制開關
- 現有 context_buffer 已在收集群組訊息，observer 是在此基礎上加 batch 整理
- Cross-chat 查詢透過 tool，權限用 config 控制

## 注意：context_buffer 與 observer_batch_size 依賴

context_buffer 有 `context_window` 上限（預設 20），超過丟舊的。
observer_batch_size 必須 ≤ context_window，否則永遠攢不到觸發量。

做法：
- observer mode 的 chatbot，context_window 自動設為 `max(context_window, observer_batch_size)`
- 共用 context_buffer，不另開獨立 buffer（避免存哪邊的問題）
- observer 整理時從 context_buffer drain，跟現有 chatbot 回話 drain 同一條路

## Changes

### 1. ChatbotConfig 加 observer 設定

```python
class ChatbotConfig(BaseModel):
    # ... existing fields ...
    observer_mode: bool = False           # 靜默模式（不回話）
    observer_batch_size: int = 10         # 幾則觸發一次整理
    observer_categories: list[str] = []   # 整理分類提示
```

```yaml
# routes.yaml
chatbots:
  信益觀察者:
    mode: observer                          # 不回話
    model: gpt-5-mini                       # 整理用，不需要最強
    observer_batch_size: 10
    observer_categories: [請假, 進料, 出料, 出貨, 工程進度, 客訴, 其他]
    tools: []                               # observer 不需要 tool
```

### 2. Hub — observer mode 判斷

```python
# hub.py receive()
if chatbot_config.observer_mode:
    # 永不觸發 chatbot，直接存 context buffer
    self._context_buffer.append(...)
    # 檢查 batch size，達標就觸發整理
    if self._context_buffer.count(route_id) >= batch_size:
        asyncio.create_task(self._process_observer_batch(route_id))
    return
```

### 3. Observer 整理 pipeline

context buffer drain → 送 LLM 整理 → 結構化存 Memory Store

```python
async def _process_observer_batch(self, route_id):
    messages = self._context_buffer.drain(route_id)
    formatted = self._context_buffer.format_context(messages)
    # 用 general-agent 或輕量 LLM 整理
    result = await self._observer_processor(route_id, formatted, categories)
    # 存到 Memory Store (新 type: observation)
    await memory_store.save(route_id, "observation", result)
```

整理結果格式：
```json
{
    "batch_time": "2026-03-26T11:00:00",
    "message_count": 10,
    "entries": [
        {
            "category": "請假",
            "who": "王大叔",
            "content": "明天請假一天",
            "timestamp": "2026-03-26T10:45:00"
        },
        {
            "category": "出料",
            "who": "小陳",
            "content": "K1 出了10桶得利特白給XX工地",
            "timestamp": "2026-03-26T10:50:00"
        }
    ],
    "summary": "本批 10 則訊息：1 則請假、1 則出料、8 則閒聊"
}
```

### 4. Memory Store — observation type

```python
class Observation(BaseModel):
    id: str
    route_id: str         # 來源群組
    batch_time: datetime
    message_count: int
    entries: list[dict]   # structured entries
    summary: str
    created_at: datetime
```

### 5. Cross-Chat Query Tool

```python
def create_query_observations_tool(memory_store, config):
    """查詢觀察者收集的資料。"""

    async def handler(invocation):
        source = args.get("source", "")      # "信益大群組" or route_id
        category = args.get("category", "")  # "請假" / "出料" / ""=全部
        days = args.get("days", 7)

        # 權限檢查：caller 的 route_id 在 allowed_consumers 裡嗎？
        caller_route = session_id → route_id
        if caller_route not in allowed_consumers[source]:
            return "無權限查詢此群組的觀察資料"

        # 查 Memory Store
        observations = await memory_store.query_observations(
            source_route_id, category, days
        )
        return format_observations(observations)
```

### 6. Config — 權限控制

```yaml
# routes.yaml
observers:
  信益大群組:
    source_group: "Cxxx"
    allowed_consumers: ["Ceead...", "Ufc68..."]  # 管理群組 + Rick 私訊
```

## File Changes

| File | Action |
|------|--------|
| `core/types.py` | ChatbotConfig 加 observer fields |
| `hub/hub.py` | observer mode 判斷 + batch trigger |
| `hub/context_buffer.py` | 加 count() method |
| `memory/types.py` | 新增 Observation model |
| `memory/store.py` | observation table + query_observations |
| `tools/builtin/query_observations.py` | **新檔** — cross-chat query tool |
| `server/__init__.py` | observer wiring |
| `config/routes.yaml` | observer chatbot + 權限 config |

## Execution Order

1. ChatbotConfig + Observation type
2. Memory Store observation table
3. Hub observer mode + batch trigger
4. Observer 整理 processor (用 general-agent pipeline 或獨立 LLM call)
5. query_observations tool
6. Config + wiring
7. E2E 測試

## Verification

1. 大群組發 10 則訊息 → observer 靜默收集 → 第 10 則觸發整理 → DB 有 observation
2. 管理群組問「請假狀況」→ query_observations → 回傳整理結果
3. 非授權群組問 → 被拒
4. observer 群組裡 bot 完全不發言
