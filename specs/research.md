# Research: Agent Gateway MVP v2

**Date**: 2026-03-18
**Spec**: [spec.md](spec.md)

本文件解決 spec 中所有「待決事項」及技術未知項。

---

## R-001：SDK Timeout / Error 行為

**Decision**: 分層錯誤處理，區分 Chat 層與 Task 層

**研究發現**（基於 github-copilot-sdk v0.1.29 原始碼分析）：

### 例外類型

| 例外 | 來源 | 意義 |
|------|------|------|
| `TimeoutError` | `send_and_wait()` | 等待 session.idle 超時（預設 60s） |
| `ProcessExitedError` | `JsonRpcClient` | CLI process 意外終止，含 stderr |
| `JsonRpcError` | `request()` | JSON-RPC 協議錯誤，含 code + message |
| `StopError` | `client.stop()` | 清理階段錯誤（ExceptionGroup） |
| `RuntimeError` | 各處 | 連線狀態異常（如 client 未連線） |

### Timeout 機制

- `send_and_wait(timeout=60)` — 預設 60 秒，可設定
- 超時後 raise `TimeoutError`，**不會中止進行中的 agent 工作**
- MCP server 有獨立 timeout（毫秒），設定在 MCPServerConfig
- **無內建 retry**：caller 必須自行實作重試

### Session 生命週期

```
create_session() → send_and_wait() → destroy() / abort()
                ↘ resume_session()（恢復既有 session）
```

- CLI process crash → `ProcessExitedError`，需 caller catch + 重建 session
- Session 錯誤 → `SESSION_ERROR` event
- 無自動重連機制

### Tool 執行錯誤

- Handler 例外被 catch → `ToolResult(resultType="failure")`
- 詳細錯誤存在 `error` 欄位，**不暴露給 LLM**（安全設計）
- Tool 不存在 → 回傳 unsupported result（不 raise）

### Chatpilot 錯誤處理策略

**Chat 層**（chatbot session）：

```
try:
    response = await session.send_and_wait(message, timeout=60)
except TimeoutError:
    → 回覆「處理超時，請稍後再試」
except ProcessExitedError:
    → 嘗試 resume_session()
    → 失敗則回覆「系統暫時不可用」
except JsonRpcError:
    → 回覆「系統錯誤」+ log 完整 error
```

**Task 層**（pipeline agent session）：

```
try:
    result = await session.send_and_wait(task_input, timeout=300)
except TimeoutError:
    → task.status = "failed"
    → push「任務超時」回原對話
except ProcessExitedError:
    → task.status = "failed"
    → push「任務執行錯誤」回原對話
```

- Chat 層 timeout 短（60s），Task 層 timeout 長（300s，可由 config 設定）
- 不實作自動 retry（MVP），但 log 所有錯誤供手動排查

**Rationale**: SDK 不提供自動重連 / retry，chatpilot 層面做簡單的 catch + 友善回覆
即可。進階的 circuit breaker / retry 留待非 MVP 階段。

**Alternatives considered**:
- 自動 retry with exponential backoff → 過度工程，MVP 不需要
- Circuit breaker pattern → 單一使用者場景不需要

---

## R-002：Node Output 系統層必填欄位

**Decision**: 最小化必填欄位，node 自由擴展

```python
class NodeOutput(TypedDict):
    status: Literal["success", "error"]
    data: Any                    # node 產出的業務資料
    error: str | None            # status="error" 時的錯誤訊息

class NodeMetadata(TypedDict, total=False):
    duration_ms: int             # 自動計算，node 不需手動填
    node_name: str               # 自動帶入，node 不需手動填
```

- `status` + `data` 是 node 唯一需要關心的欄位
- `error` 只在 `status="error"` 時填寫
- `duration_ms` 和 `node_name` 由 PipelineExecutor 自動注入

**Rationale**: Node 開發者只需回傳 `{"status": "success", "data": {...}}` 即可。
系統元資料由框架自動加入，降低 node 開發門檻。

**Alternatives considered**:
- 豐富的元資料（token usage, model used, etc.）→ 留待 node 自己加在 data 內
- Pydantic model 強制驗證 → 增加 node 開發複雜度，MVP 用 TypedDict 即可

---

## R-003：completion_condition 表達格式

**Decision**: Python callable，不建 DSL

```python
# Pipeline 定義中
class InventoryReportPipeline:
    max_iterations: int = 3

    def should_continue(self, context: PipelineContext) -> bool:
        """迴圈跳出條件 — 回傳 True 繼續、False 停止"""
        return (
            context.iteration < self.max_iterations
            and context.last_output.status == "success"
        )
```

- 每個 pipeline 在 code 中定義自己的跳出條件
- PipelineExecutor 在每次 iteration 後呼叫 `should_continue()`
- 硬上限：`max_iterations`（config 設定，預設 10）作為安全閥

**Rationale**: Pipeline 是「精心調教驗證過的」，不開放使用者自訂組合。
跳出條件與 pipeline 邏輯緊耦合，code > DSL。

**Alternatives considered**:
- YAML DSL (`condition: "iteration < 3 AND last_status == success"`) → 解析複雜，
  表達力受限，debug 困難
- JSON schema 條件式 → 同上

---

## R-004：Memory Tool 儲存後端

**Decision**: JSON file per task，存放於 `data/memory/`

```
data/memory/
├── {task_id}/
│   ├── memory.json      # key-value 記憶儲存
│   └── context.json     # pipeline context snapshot
```

```python
class MemoryStore:
    async def get(self, task_id: str, key: str) -> Any
    async def set(self, task_id: str, key: str, value: Any) -> None
    async def list_keys(self, task_id: str) -> list[str]
    async def delete(self, task_id: str, key: str) -> None
```

- 每個 task 獨立目錄，task 完成後可選擇保留或清除
- JSON 格式便於人工檢查和 debug
- 讀寫透過 async file I/O（`aiofiles` 或 `asyncio.to_thread`）

**Rationale**: MVP 規模小，JSON file 足夠。SQLite 適合結構化查詢但
Memory Tool 的用途是 key-value 存取，JSON 更直觀。

**Alternatives considered**:
- SQLite → 過重，Memory Tool 是 KV 操作不需要 SQL
- Redis → 外部依賴，MVP 不需要
- In-memory dict → 重啟丟失，不符合「跨 node 脈絡保留」需求

---

## R-005：Task History 持久化方式

**Decision**: SQLite + WAL mode

```sql
CREATE TABLE tasks (
    id          TEXT PRIMARY KEY,     -- UUID
    status      TEXT NOT NULL,        -- queued | running | completed | failed
    created_at  TEXT NOT NULL,        -- ISO 8601
    started_at  TEXT,
    completed_at TEXT,
    duration_ms INTEGER,
    input_summary  TEXT,              -- 使用者原始請求摘要
    output_summary TEXT,              -- 結果摘要（供 chatbot tool 查詢）
    output_full    TEXT,              -- 完整結果 JSON
    chat_route_id  TEXT NOT NULL,     -- 對應的對話路由（用於 push 回去）
    pipeline_name  TEXT NOT NULL,     -- 執行的 pipeline 名稱
    error          TEXT               -- 失敗原因
);

CREATE INDEX idx_tasks_status ON tasks(status);
CREATE INDEX idx_tasks_chat_route ON tasks(chat_route_id);
```

- 單一檔案 `data/tasks.db`，WAL mode 支援並行讀寫
- Summary 欄位供 chatbot task history tool 快速查詢
- Full output 分開存放，大查詢時才讀取

**Rationale**: Task history 需要結構化查詢（按狀態、按對話、按時間）
和持久化（重啟不丟失）。SQLite 是最輕量的選擇，無外部依賴。

**Alternatives considered**:
- JSON files → 查詢困難（需掃描所有檔案），狀態更新需覆寫整個檔案
- PostgreSQL → 外部依賴，自架場景過重
- In-memory + periodic dump → 有丟失風險

---

## R-006：Task UUID 生成策略

**Decision**: `uuid.uuid4()`（隨機 UUID）

- 標準 library，無外部依賴
- 128-bit 隨機，碰撞機率可忽略
- 對使用者顯示時可截取前 8 字元（如 `a1b2c3d4`）

**Rationale**: 單機場景無需分散式 ID 生成器。UUID4 簡單可靠。

**Alternatives considered**:
- ULID（時間排序）→ 需額外依賴，MVP 不需時間排序
- 自增 ID → SQLite auto-increment 可用但 ID 可預測
- nanoid → 需額外依賴

---

## R-007：Queue 滿載時的 Backpressure 策略

**Decision**: `max_queue_size` config + 拒絕新任務

```yaml
scheduler:
  concurrent_runners: 2
  max_queue_size: 100    # 預設 100
```

- Queue 滿時，chatbot 回覆「系統忙碌，請稍後再試」
- `max_queue_size` 由 config 設定，預設 100
- 計數器檢查在 `enqueue()` 入口

**Rationale**: MVP 為小群組場景，100 個排隊任務已是極端情況。
簡單的拒絕策略足夠。

**Alternatives considered**:
- 優先級隊列 → 增加複雜度，MVP 不需要
- 動態調整 runner pool → 過度工程
- 超時自動丟棄 → 使用者體驗差，不如直接拒絕

---

## R-008：Context Buffer 結構化格式

**Decision**: 結構化 prefix + 角色標記

注入 chatbot 時的格式：

```
[群組近期對話]
[背景] UserA (14:30): 今天天氣很好
[背景] UserB (14:32): 對啊，要不要出去玩
[背景] UserC (14:35): 我覺得可以去海邊
[busy 期間] UserD (14:36): @bot 幫我也查一下
---
[以下是直接對你說的訊息]
```

- `[背景]`：非 @bot 的群組訊息，低優先級上下文
- `[busy 期間]`：chatbot busy 時收到的 @bot 訊息，中優先級
- 分隔線 `---` 之後是當前直接觸發的 @bot 訊息
- 時間戳和使用者名稱幫助 chatbot 理解對話脈絡

**注入方式**：串接在 user message 前面

SDK `send_and_wait()` 只接受 `message: str`，無獨立 context 參數。
Context buffer 直接串在 user message 前面，以 `---` 分隔：

```python
context_prefix = format_context_buffer(buffer_messages)
prompt = f"{context_prefix}\n---\n{user_message}"
await session.send_and_wait(prompt, timeout=60)
```

搭配 chatbot system_message 加入指引：

```
群組對話中，標記 [背景] 的內容是其他人的閒聊，供你參考但不需回應。
--- 分隔線之後是直接對你說的訊息，請優先處理。
```

**Rationale**: 結構化標記讓 LLM 能區分背景閒聊和直接請求。
SDK 不提供 context injection API，串接 user message 是唯一可行方式。

**Alternatives considered**:
- System message 動態更新 → SDK 的 system_message 是 session-level 設定，
  不支援 per-message 覆蓋
- JSON 格式 → LLM 處理 JSON 上下文效果差，自然語言更好
- 無標記混入 → chatbot 無法區分直接 vs 背景訊息
- 分開成多個 user message → SDK 不支援一次送多條 user message

---

## R-009：v1 Code 可重用性評估

**研究發現**（基於 v1 全量程式碼分析）：

### KEEP（直接可用或小幅擴展）

| 模組 | 遷移方式 |
|------|----------|
| `core/types.py` | 擴展 Task/TaskResult 型別；RouteConfig → BindingConfig |
| `core/errors.py` | 新增 SchedulerError, BindingError |
| `channels/adapter.py` | 擴展 push 方法 |
| `channels/line/parser.py` | 直接沿用 |
| `channels/line/__init__.py` | 擴展 push API 呼叫 |
| `server/session_gate.py` | Chat 層直接沿用 |

### REFACTOR（核心邏輯可用，結構需調整）

| 模組 | 遷移方式 |
|------|----------|
| `agents/base.py` | Protocol 改為 PipelineNode 介面 |
| `sdk/session_manager.py` | 拆出 session wrapper utility，廢棄 singleton |
| `dispatch/route_loader.py` | RouteWatcher → ConfigWatcher，泛化 |
| `processing/command_handler.py` | fuzzy matching 提取為 utility |
| `processing/processor.py` | 提取 pipeline pattern，重建 dual chat/task |

### REPLACE（需全新實作）

| 模組 | 原因 |
|------|------|
| `cli/main.py` | v2 需支援 binding 解析 + task dispatch |
| `agents/general/__init__.py` | 改為 pipeline node 結構 |
| `server/__init__.py` | 元件圖完全不同 |

**預估重用率**：~35% 直接沿用、~40% 重構、~25% 重寫

---

## R-010：Script Node I/O 規範

**Decision**: 延後。Spec 明確說「不限定固定 node type」，
每個 node 實作 PipelineNode Protocol（`async execute(input: dict) -> NodeOutput`）
即可。Script node 如有需要，屆時定義 ScriptNode subclass。

---

## 未解決項目

無。所有 spec 待決事項已解決。
