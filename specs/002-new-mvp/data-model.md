# Data Model: Agent Gateway MVP v2

**Date**: 2026-03-18
**Spec**: [spec.md](spec.md) | **Research**: [research.md](research.md)

---

## 核心實體

### Message（統一訊息格式）

來自任何平台的 inbound 訊息，經 adapter 轉換後的統一格式。

| 欄位 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `text` | `str` | Y | 訊息文字內容 |
| `user_id` | `str` | Y | 發送者 ID（平台 user ID） |
| `user_name` | `str` | N | 發送者顯示名稱 |
| `platform` | `str` | Y | 平台標識（`"line"`, `"mock"`, `"cli"`） |
| `group_id` | `str \| None` | N | 群組 ID（私聊時為 None） |
| `conversation_id` | `str` | Y | 對話 ID（群組 = group_id，私聊 = user_id） |
| `is_mention` | `bool` | Y | 是否 @bot mention |
| `platform_context` | `dict[str, Any]` | N | 平台專屬資料（如 LINE reply_token） |
| `timestamp` | `datetime` | Y | 訊息時間 |

**驗證規則**：
- `text` 不可為空白（strip 後長度 > 0）
- `platform` 必須為已知值
- `conversation_id` 由 adapter 產生（群組用 group_id，私聊用 user_id）

**v1 差異**：新增 `is_mention`、`user_name`、`timestamp` 欄位

---

### Response（統一回應格式）

Chatbot 或系統產出的回應，經 adapter 轉換為平台格式後送出。

| 欄位 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `text` | `str` | Y | 回應文字內容 |
| `attachments` | `list[Attachment]` | N | 附件（MVP 僅文字，保留擴展） |

**驗證規則**：
- `text` 不可為空

---

### ChatRoute（對話路由資訊）

Message Hub 路由後產出的對話上下文，包含 binding 結果。

| 欄位 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `route_id` | `str` | Y | 路由唯一 ID（`{platform}:{conversation_id}`） |
| `chatbot_name` | `str` | Y | 匹配到的 chatbot 類型名稱 |
| `platform` | `str` | Y | 平台標識 |
| `conversation_id` | `str` | Y | 對話 ID |
| `binding_score` | `int` | Y | 匹配分數 |

**驗證規則**：
- `chatbot_name` 必須存在於 config 的 `chatbots` 定義中

---

### ChatbotConfig（Chatbot 設定）

Config 中定義的 chatbot 宣告。

| 欄位 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `name` | `str` | Y | Chatbot 類型名稱（唯一） |
| `model` | `str` | Y | 預設 LLM 模型 |
| `system_message` | `str` | Y | System prompt |
| `tools` | `list[str]` | N | 可用 tool 名稱清單 |
| `task_history` | `bool` | N | 是否啟用任務歷史查詢 tool（預設 False） |
| `context_window` | `int` | N | Context buffer 大小（預設 20） |

---

### Binding（路由綁定規則）

定義訊息 match 條件與對應 chatbot 的映射關係。

| 欄位 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `match` | `dict[str, str]` | N | 匹配條件（platform, group_id, user_id） |
| `chatbot` | `str` | Y | 對應的 chatbot 類型名稱 |

**計分規則**（`match_weights`）：

| 維度 | 預設分數 | 說明 |
|------|----------|------|
| `group_id` | 10 | 群組級別匹配 |
| `user_id` | 8 | 使用者級別匹配 |
| `platform` | 5 | 平台級別匹配 |

- 總分 = 所有匹配維度的分數加總
- 無 `match` 欄位 = 預設 binding（score = 0）
- 最高分 binding 勝出
- 分數表可在 config 中擴展新維度

---

### TaskInfo（任務資訊）

Scheduler 管理的異步任務。

| 欄位 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `id` | `str` | Y | UUID（uuid4） |
| `status` | `TaskStatus` | Y | 任務狀態 |
| `created_at` | `datetime` | Y | 建立時間 |
| `started_at` | `datetime \| None` | N | 開始執行時間 |
| `completed_at` | `datetime \| None` | N | 完成時間 |
| `duration_ms` | `int \| None` | N | 執行耗時（毫秒） |
| `pipeline_name` | `str` | Y | 執行的 pipeline 名稱 |
| `input_summary` | `str` | Y | 使用者原始請求摘要 |
| `input_data` | `dict` | Y | 完整輸入參數 |
| `output_summary` | `str \| None` | N | 結果摘要 |
| `output_full` | `dict \| None` | N | 完整結果 |
| `chat_route_id` | `str` | Y | 對應的對話路由 ID（用於 push） |
| `error` | `str \| None` | N | 失敗原因 |

**狀態轉換**：

```
queued → running → completed
                 → failed
```

- `queued`：已進入 queue 等待執行
- `running`：runner 已取出執行中
- `completed`：執行成功，output 已填入
- `failed`：執行失敗，error 已填入

**驗證規則**：
- 狀態只能單向轉換（不可回退）
- `completed` 時 `output_summary` 必填
- `failed` 時 `error` 必填

---

### ToolDefinition（Tool 定義）

Tool Factory 管理的 tool 註冊資訊。

| 欄位 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `name` | `str` | Y | Tool 名稱（唯一） |
| `description` | `str` | Y | Tool 描述（給 LLM 看） |
| `parameters` | `dict` | Y | JSON Schema 格式的參數定義 |
| `handler` | `ToolHandler` | Y | Tool 執行函式 |
| `access_level` | `AccessLevel` | Y | 存取級別 |

**存取級別**（AccessLevel）：

| 級別 | 值 | 誰可用 |
|------|-----|--------|
| `global` | 1 | 任何 context |
| `chatbot_only` | 2 | 僅 chatbot session |
| `agent_team_only` | 3 | 僅 pipeline 內部 agent |

**驗證規則**：
- `name` 全域唯一
- Agent team 內部 agent 不可呼叫 `chatbot_only` 級別的 agent team tool（防止遞迴）

---

### AgentConfig（Pipeline Agent 設定）

Config 中定義的 pipeline 內部 agent 宣告。

| 欄位 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `name` | `str` | Y | Agent 名稱（唯一） |
| `model` | `str` | Y | LLM 模型 |
| `workdir` | `str \| None` | N | 工作目錄 |
| `tools` | `list[str]` | N | 可用 tool 名稱清單 |

---

### NodeOutput（Pipeline Node 輸出）

Pipeline 中每個 node 的標準輸出格式。

| 欄位 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `status` | `Literal["success", "error"]` | Y | 執行結果狀態 |
| `data` | `Any` | Y | 業務資料 |
| `error` | `str \| None` | N | 錯誤訊息 |

**系統自動注入的元資料**（由 PipelineExecutor 加入，node 不需處理）：
- `duration_ms`：執行耗時
- `node_name`：node 名稱

---

### ContextMessage（Context Buffer 儲存單元）

Context buffer 中的單條訊息記錄。

| 欄位 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `user_id` | `str` | Y | 發送者 ID |
| `user_name` | `str` | Y | 發送者顯示名稱 |
| `text` | `str` | Y | 訊息內容 |
| `timestamp` | `datetime` | Y | 訊息時間 |
| `message_type` | `ContextMessageType` | Y | 訊息分類 |

**訊息分類**（ContextMessageType）：

| 分類 | 說明 |
|------|------|
| `background` | 非 @bot 的群組閒聊 |
| `mention_busy` | @bot 但 chatbot busy 時的訊息 |

---

### SchedulerConfig（Scheduler 設定）

| 欄位 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `concurrent_runners` | `int` | Y | Runner pool 大小（預設 2） |
| `max_queue_size` | `int` | N | Queue 最大長度（預設 100） |
| `task_timeout` | `int` | N | 單一任務 timeout 秒數（預設 300） |

---

## 實體關係

```
Binding ──match──→ ChatbotConfig
    │                    │
    │                    ├── tools ──→ ToolDefinition (via ToolFactory)
    │                    │                   │
    │                    │                   ├── submit_task tool ──→ TaskScheduler
    │                    │                   └── task_history tool ──→ TaskStore
    │                    │
    │                    └── session ──→ SDK Session (per ChatRoute)
    │
Message ──route──→ ChatRoute ──→ ChatbotConfig
    │
    └── context ──→ ContextMessage[] (per chatbot, sliding window)

TaskInfo ──pipeline──→ AgentConfig[] ──→ SDK Session (per node)
    │                                        │
    │                                        └── tools ──→ ToolDefinition
    │
    └── result ──push──→ ChatRoute ──→ ChannelAdapter

ToolFactory ──registry──→ ToolDefinition[]
    │
    ├── global tools ──→ 任何 session
    ├── chatbot_only ──→ chatbot session only
    └── agent_team_only ──→ pipeline agent only
```

---

## 持久化策略

| 資料 | 儲存方式 | 位置 | 說明 |
|------|----------|------|------|
| Task history | SQLite (WAL) | `data/tasks.db` | 結構化查詢、重啟不丟失 |
| Memory Tool | JSON files | `data/memory/{task_id}/` | Per-task KV 儲存 |
| Context buffer (cold) | JSON files | `data/context/{route_id}/` | 群組對話歷史 |
| Config | YAML | `config/routes.yaml` | 熱重載 |
| Secrets | .env | `.env` | 環境變數 |

**In-memory 資料**（重啟丟失，可接受）：
- Chatbot busy/idle 狀態
- Context buffer hot layer
- Task queue（進行中的任務會標記 failed）
- SDK sessions（需重建）
