# 資料模型：通用 Agent Gateway MVP

**Branch**: `001-agent-gateway-mvp` | **Date**: 2026-03-03
**Updated**: 2026-03-03 — TypeScript → Python/Pydantic

---

## 核心領域模型

### 1. Message（統一輸入格式）

```python
from pydantic import BaseModel, Field
from typing import Literal

Platform = Literal["line"] | str  # 可擴充

class LinePlatformContext(BaseModel):
    reply_token: str              # LINE reply token（60 秒有效期）
    message_id: str               # LINE message ID
    timestamp: int                # Webhook 送達時間（Unix ms）

class Message(BaseModel):
    # 訊息本體
    text: str                     # 文字內容（MVP 僅支援文字）

    # 來源識別
    user_id: str                  # 使用者識別碼（平台 user ID）
    platform: Platform            # 平台標識（"line" | "telegram" 等）
    conversation_id: str | None = None  # 群組/對話識別；私聊時為 None（以 user_id 路由）

    # 平台 Context（各平台特有資料，類型由 adapter 決定）
    platform_context: LinePlatformContext | dict = Field(default_factory=dict)
```

**驗證規則**：
- `text` 不得為空字串。
- `platform` 不得為空字串。
- `conversation_id` 為 `None` 時，路由以 `user_id` 作為 fallback key。

**狀態轉換**：無（Message 為 immutable value object，Pydantic frozen model）

---

### 2. Response（統一輸出格式）

```python
class Attachment(BaseModel):
    type: Literal["image", "file"]
    url: str

class Response(BaseModel):
    text: str                     # 回覆文字
    attachments: list[Attachment] = Field(default_factory=list)  # MVP: 永遠為空 list
```

**驗證規則**：
- `text` 不得為空字串。
- MVP 階段 `attachments` 永遠為 `[]`。

---

### 3. RouteMap（路由表）

```python
class KeywordMapping(BaseModel):
    keyword: str                  # 比對字串（substring 比對）
    agent_name: str               # 命中時路由至此 agent

class RouteRule(BaseModel):
    # 路由識別鍵
    platform: Platform            # 平台標識
    conversation_id: str | None = None  # 群組識別；None 代表「私聊」規則

    # 路由行為
    keywords: list[KeywordMapping] = Field(default_factory=list)  # 關鍵字 → agent 對應
    fallback_agent: str | None = None  # 未命中關鍵字時的 fallback agent；None = 靜默忽略

class RouteMap(BaseModel):
    routes: list[RouteRule] = Field(default_factory=list)
```

**routes.yaml 範例**：
```yaml
routes:
  - platform: line
    conversationId: "C1234567890abcdef"   # 群組 A
    keywords:
      - keyword: "庫存"
        agentName: warehouse-agent
      - keyword: "報表"
        agentName: report-agent
    fallbackAgent: general-agent   # 未命中關鍵字 → general-agent

  - platform: line
    conversationId: "C0987654321fedcba"   # 群組 B（只有 fallback）
    keywords: []
    fallbackAgent: general-agent

  - platform: line
    conversationId: null                  # 私聊規則
    keywords: []
    fallbackAgent: general-agent
```

> **Note**: YAML 使用 camelCase key（`conversationId`, `agentName`, `fallbackAgent`），route_loader 解析時轉為 snake_case 對應 Pydantic model。透過 Pydantic `model_config = ConfigDict(alias_generator=to_camel)` 或 `Field(alias="...")` 處理。

**驗證規則**：
- `platform` 不得為空字串。
- `keyword` 不得為空字串。
- `agent_name` 與 `fallback_agent` 必須存在於已註冊的 agent 清單中（啟動時驗證）。
- 同一 `(platform, conversation_id)` 組合在 `routes` 中不得重複。

**狀態轉換（熱重載）**：
```
[初始化] → 讀取 routes.yaml → RouteMap loaded
[檔案變更] → watchdog 偵測 → YAML 解析
   ├── 解析成功 → atomic 替換 current_route_map
   └── 解析失敗 → 保留 current_route_map，記錄錯誤
```

---

### 4. PendingMessage（暫存佇列項目）

```python
class PendingMessage(BaseModel):
    session_id: str               # "{platform}-{conversationId}"
    content: str                  # agent 已完成的回覆文字
    enqueued_at: int              # 進入佇列時間（Unix ms）
    ttl_ms: int = 1_800_000      # 過期時長（預設 30 分鐘）
```

**狀態轉換**：
```
[agent 完成，reply token 已過期] → enqueue(PendingMessage)
[下一則訊息到達，同 session_id]  → dequeue + 優先補送
[ttl 過期，無後續訊息]           → 靜默丟棄
```

**儲存**：in-memory `dict[str, list[PendingMessage]]`（MVP 不持久化）

---

### 5. Session（Copilot SDK 管理，非自行維護）

Session 由 `github-copilot-sdk` 自動管理，本系統只需維護 `session_id`：

```
session_id = "{platform}-{conversation_id}"
# 私聊："{platform}-{user_id}"

# 例：
"line-C1234567890abcdef"   # LINE 群組
"line-U9876543210fedcba"   # LINE 私聊
```

SDK 自動處理：
- 對話歷史持久化（workspace directory）
- Context window compaction
- Multi-turn 上下文恢復

---

## 介面關係圖

```
Channel Layer              Core Layer                SDK Layer
─────────────              ──────────                ─────────
LINE Webhook ──────────→  Message
                               │
                               ▼
                          RouteMap ──────────────→  session_id
                               │                        │
                               ▼                        ▼
                          Agent (BaseAgent)  ←──  CopilotSession
                               │
                               ▼
                          Response
                               │
LINE Reply API ◄───────────────┘
(or PendingQueue)
```

---

## 路由決策流程

```
Message 到達
    │
    ├── 1. 查詢 RouteRule: (platform, conversation_id) 精確比對
    │       ├── 命中 → 進入關鍵字比對
    │       └── 未命中 → 嘗試 (platform, None) 規則（私聊 fallback）
    │
    ├── 2. 關鍵字比對（substring 比對，按 keywords 順序）
    │       ├── 命中 → 路由至對應 agent
    │       └── 未命中 → 檢查 fallback_agent
    │
    └── 3. fallback_agent
            ├── 有設定 → 路由至 fallback_agent
            └── None  → 靜默忽略（不消耗 AI token）
```
