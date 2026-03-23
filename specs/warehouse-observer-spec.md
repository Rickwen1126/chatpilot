# 功能規格：Observer Bot

**Created**: 2026-03-23
**Status**: Draft

## 一、產品定位

為 chatpilot 群組 chatbot session 新增「觀察者」機制。觀察者是獨立的 chatbot session，被動接收群組訊息，整理後存入 Memory Store，為主 chatbot 提供結構化的長期記憶。

**核心概念**：

- 主 chatbot 負責即時對話，觀察者負責背景整理
- 觀察者不介入對話流程，異步處理不影響主 chatbot 回覆速度
- 觀察者的產出寫入主 route 的 Memory Store，與主 chatbot 共享資料

**設計原則**：

- 以 ContextBuffer 的 callback 機制驅動，不改變既有訊息流程
- 觀察者是獨立 chatbot session，各自有自己的 model 和 system_message
- 預設靜默（不回覆），可配置為 push 通知

---

## 二、使用者情境

### US1：群組對話自動整理

群組成員日常聊天，觀察者在背景接收訊息，整理成結構化記錄存入 Memory Store。主 chatbot 被 @mention 時可參考這些記錄。

> （群組成員討論了 30 則關於下週活動的訊息）
> （ContextBuffer 淘汰舊訊息時，batch 送給觀察者）
> （觀察者整理：「3/23 討論了下週六活動，地點暫定大安森林公園，預算 3000 元」）
> （記錄存入 Memory Store type=observation）
>
> User: @bot 上週大家聊了什麼？
> Bot:（查詢 Memory Store）上週主要討論了下週六活動的安排...

### US2：@mention 觸發時的對話摘要

使用者 @bot 觸發 drain 時，drain 的訊息同步送給觀察者整理。

> （群組累積了 20 則訊息）
> User: @bot 幫我總結一下
> Bot:（即時回覆，使用 drain 出的 context）
> （同時，觀察者也收到同一批訊息，異步整理存入 Memory Store）

### US3：靜默觀察 + 可選 push 通知

預設觀察者不回覆。若配置 `reply: true`，觀察者處理完後可 push 通知回群組。

> （觀察者配置 reply: true）
> （觀察者偵測到重要資訊）
> Bot: [推送] 注意：剛才對話中提到週五截止的報告，目前還沒人認領。

---

## 三、功能需求

### ContextBuffer Callback

- **FR-001**：ContextBuffer 新增 `on_evict` callback，sliding window 淘汰舊訊息時觸發，傳入被淘汰的訊息 batch
- **FR-002**：ContextBuffer 的 `drain()` 新增 `on_drain` callback，drain 時觸發，傳入被 drain 的訊息副本
- **FR-003**：callback 簽名統一為 `async (route_id: str, messages: list[ContextMessage]) -> None`
- **FR-004**：callback 執行失敗 MUST NOT 影響主流程（catch + log error）

### Observer Session

- **FR-005**：觀察者是獨立的 chatbot session，有自己的 model、system_message、session 生命週期
- **FR-006**：觀察者 session_id 格式：`{route_id}-obs-{N}`（N 從 1 起算）
  - 範例：主 chatbot `line:C5aa023b...`，觀察者 `line:C5aa023b...-obs-1`
- **FR-007**：觀察者處理 MUST 異步執行（`asyncio.create_task`），不 blocking 主 chatbot
- **FR-008**：一個群組可註冊多個觀察者，各自獨立處理同一批訊息

### Memory Store 寫入

- **FR-009**：觀察者的 Memory Store 寫入 MUST 使用主 route_id（非觀察者 session_id），確保資料在同一個群組下共享
- **FR-010**：新增 Memory Store type `observation`，欄位：id, route_id, text, source（evict / drain）, observer_name, created_at
- **FR-011**：觀察者可使用自訂 type（如 `summary`），由 system_message 指導 LLM 決定存入哪種 type

### 回覆機制

- **FR-012**：預設 `reply: false`（靜默），觀察者處理完不產出回覆
- **FR-013**：配置 `reply: true` 時，觀察者的回覆走 `hub.push(route_id, response)`（主動推送，無 reply token）
- **FR-014**：push 失敗時 log error，不影響觀察者的 Memory Store 寫入

### 配置

- **FR-015**：chatbot config 新增 `observers` 欄位，定義該 chatbot 的觀察者列表
- **FR-016**：每個 observer config 包含：name、model、system_message、reply（bool, default false）
- **FR-017**：觀察者配置範例：

```yaml
chatbots:
  buddy:
    model: gpt-4.1
    system_message: "..."
    tools: [...]
    context_window: 50
    observers:
      - name: history-recorder
        model: claude-haiku-4.5
        system_message: |
          你是群組對話觀察者。你會收到一批群組對話訊息。
          請整理出重要資訊（決定、待辦、重要事件），
          用 save_memo tool 存入記錄。
          不需要回覆任何內容。
        reply: false
      - name: topic-tracker
        model: claude-haiku-4.5
        system_message: |
          你是話題追蹤者。分析群組對話的主題變化，
          記錄每個話題的摘要和參與者。
        reply: false
```

---

## 四、資料流

```
群組訊息 → ContextBuffer.append()
  │
  ├── 正常路徑：@bot → drain() → 主 chatbot 回覆
  │                      │
  │                      └── on_drain callback → 訊息副本 → 觀察者（異步）
  │
  └── 淘汰路徑：buffer 超過 context_window
                      │
                      └── on_evict callback → 被淘汰的訊息 → 觀察者（異步）

觀察者處理流程：
  收到訊息 batch
    → 觀察者 chatbot session 處理（整理、摘要、分類）
    → 透過 tool 存入主 route_id 的 Memory Store
    → reply: false → 結束
    → reply: true  → hub.push(route_id, response)
```

---

## 五、Session ID 設計

| 角色 | session_id 格式 | 範例 |
|------|----------------|------|
| 主 chatbot | `{route_id}` | `line:C5aa023b...` |
| 觀察者 1 | `{route_id}-obs-1` | `line:C5aa023b...-obs-1` |
| 觀察者 2 | `{route_id}-obs-2` | `line:C5aa023b...-obs-2` |

SDK session_id 轉換（同主 chatbot 規則）：將 `:` 替換為 `-`。

---

## 六、既有模組影響評估

| 既有模組 | 影響 | 改動 |
|---------|------|------|
| ContextBuffer | 中等 | 新增 on_evict / on_drain callback；append 淘汰時呼叫 on_evict；drain 時呼叫 on_drain |
| Hub (InMemoryMessageHub) | 小 | 接 callback → 分發給觀察者 |
| ChatbotManager | 小 | 支援建立 observer session（session_id 格式 `{route_id}-obs-{N}`） |
| ChatbotConfig (types.py) | 小 | 新增 `observers` 欄位 |
| MemoryStore | 小 | 註冊新 type `observation`（已有泛用 CRUD） |
| ToolFactory | 無 | 觀察者使用既有 tool（save_memo 等） |
| Adapters | 無 | 不動（push 已有） |
| Router | 無 | 不動 |

---

## 七、實作要點

### ContextBuffer 改動

```python
class ContextBuffer:
    def __init__(
        self,
        default_window: int = 20,
        data_dir: Path | None = None,
        on_evict: Callable[[str, list[ContextMessage]], Coroutine] | None = None,
        on_drain: Callable[[str, list[ContextMessage]], Coroutine] | None = None,
    ) -> None:
        ...
        self._on_evict = on_evict
        self._on_drain = on_drain

    async def append(self, route_id: str, ctx_msg: ContextMessage) -> None:
        buf = self._buffers[route_id]
        buf.append(ctx_msg)
        window = self._get_window(route_id)
        if len(buf) > window:
            evicted = buf[:-window]  # 被淘汰的訊息
            self._buffers[route_id] = buf[-window:]
            if self._on_evict and evicted:
                try:
                    await self._on_evict(route_id, evicted)
                except Exception:
                    logger.exception("on_evict callback failed for %s", route_id)

    async def drain(self, route_id: str) -> list[ContextMessage]:
        messages = self._buffers.pop(route_id, [])
        if self._on_drain and messages:
            try:
                await self._on_drain(route_id, list(messages))  # 副本
            except Exception:
                logger.exception("on_drain callback failed for %s", route_id)
        return messages
```

注意：`append` 變為 async method（需同步更新 Hub 的呼叫端）。

### Hub 接線

Hub 初始化時設定 ContextBuffer 的 callback，callback 內部查找 route 對應的觀察者配置，建立或取得 observer session，將訊息 batch 送入處理。

### Observer Session 建立

ChatbotManager 支援以 observer config 建立 session：

- session_id 使用 `{route_id}-obs-{N}` 格式
- model、system_message 來自 observer config
- tools 使用 Memory Store 相關 tool（save_memo 等）
- session 獨立於主 chatbot session

### 觀察者訊息注入格式

觀察者收到的訊息 batch 以結構化格式注入：

```
[觀察批次 — 來源: evict/drain]
UserA (14:30): 今天天氣真好
UserB (14:31): 對啊，下午要不要出去走走
UserC (14:32): 好啊，去大安森林公園？
...
（共 N 則訊息）

請根據以上對話內容進行整理。
```

---

## 八、範圍界定

### 包含

- ContextBuffer on_evict / on_drain callback 機制
- Observer session 建立與生命週期管理
- Observer 訊息 batch 處理（異步）
- routes.yaml observers 配置欄位
- Memory Store `observation` type

### 不包含

- 觀察者之間的協調（各自獨立）
- 觀察者的 context buffer（觀察者不累積上下文，每次收到 batch 獨立處理）
- 觀察者的 busy/idle 管理（觀察者永遠接收，不拒絕）
- 觀察者的錯誤重試（失敗只 log）
- 觀察者的 Web UI 管理
- 動態新增/移除觀察者（需重載 config）

---

## 九、成功標準

- **SC-001**：群組訊息超過 context_window 時，被淘汰的訊息自動送給觀察者處理
- **SC-002**：@bot 觸發 drain 時，drain 的訊息同步送給觀察者處理
- **SC-003**：觀察者處理不影響主 chatbot 回覆延遲（異步執行）
- **SC-004**：觀察者的 Memory Store 寫入使用主 route_id，主 chatbot 可查詢
- **SC-005**：觀察者 callback 失敗不影響主 chatbot 正常運作
- **SC-006**：配置 reply: true 的觀察者可成功 push 訊息回群組

---

## 十、依賴與假設

### 依賴

- 既有 ContextBuffer sliding window 和 drain 機制
- 既有 ChatbotManager session 建立流程
- 既有 hub.push() 主動推送能力
- 既有 MemoryStore CRUD 介面
- 既有 ToolFactory 的 save_memo 等 tool

### 假設

- 觀察者使用低成本模型（如 claude-haiku-4.5），batch 處理成本可接受
- 觀察者處理延遲不敏感（秒級到分鐘級皆可）
- MVP 觀察者數量少（每個 chatbot 1-3 個），不需並發控制
- 觀察者 session 生命週期跟隨主 chatbot session（主 session 銷毀時一併銷毀觀察者 session）
