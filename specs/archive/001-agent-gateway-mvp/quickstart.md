# Quickstart：通用 Agent Gateway MVP

**Branch**: `001-agent-gateway-mvp` | **Date**: 2026-03-03
**Updated**: 2026-03-03 — TypeScript → Python/uv/FastAPI

---

## 前置需求

| 需求 | 版本 | 說明 |
|------|------|------|
| Python | 3.11+ | [python.org](https://www.python.org) |
| uv | latest | [docs.astral.sh/uv](https://docs.astral.sh/uv/) |
| GitHub Copilot 訂閱 | 任意（含免費方案）| agent 執行引擎 |
| LINE Official Account | Messaging API channel | [LINE Developers Console](https://developers.line.biz) |
| cloudflared | latest | 提供外部 HTTPS tunnel 給 LINE webhook |

---

## 1. 環境設定

### 複製設定範本

```bash
cp .env.example .env
```

編輯 `.env`：

```bash
# LINE Messaging API
LINE_CHANNEL_SECRET=your_channel_secret
LINE_CHANNEL_ACCESS_TOKEN=your_channel_access_token

# GitHub Copilot SDK
GITHUB_TOKEN=your_github_token    # GitHub PAT 或 Copilot token

# Gateway 設定（可選，有預設值）
PORT=3000
REPLY_TIMEOUT_MS=20000            # 20 秒逾時（可調整）
PENDING_QUEUE_TTL_MS=1800000      # 30 分鐘後靜默丟棄
```

### 設定路由表

```bash
cp config/routes.example.yaml config/routes.yaml
```

編輯 `config/routes.yaml`：

```yaml
routes:
  - platform: line
    conversationId: "C1234567890abcdef"   # 你的群組 ID
    keywords:
      - keyword: "你好"
        agentName: general-agent
    fallbackAgent: general-agent
```

> **如何取得群組 ID**：將 bot 加入群組後，bot 收到的第一則訊息的 webhook payload 中可找到 `groupId`。

---

## 2. 安裝與啟動

```bash
# 安裝依賴（uv 自動建立 virtualenv）
uv sync

# 開發模式（auto-reload）
uv run uvicorn chatpilot.server:app --reload --port 3000

# 正式模式
uv run uvicorn chatpilot.server:app --host 0.0.0.0 --port 3000
```

伺服器啟動後輸出類似：
```
INFO:     Uvicorn running on http://0.0.0.0:3000 (Press CTRL+C to quit)
[gateway] Webhook endpoint: POST /webhook/line
[gateway] Route map loaded: 1 route(s) from config/routes.yaml
```

---

## 3. 設定 LINE Webhook

### 啟動 cloudflared tunnel

```bash
cloudflared tunnel --url http://localhost:3000
```

取得 HTTPS URL（例：`https://xxxx.trycloudflare.com`）。

### 在 LINE Developers Console 設定 Webhook

1. 前往 [LINE Developers Console](https://developers.line.biz)
2. 選擇你的 Messaging API channel
3. 設定 Webhook URL：`https://xxxx.trycloudflare.com/webhook/line`
4. 啟用 Webhook（Use Webhook: ON）
5. 點擊「Verify」確認連線成功

---

## 4. 測試 — CLI 模式

無需設定 LINE 也可測試 agent：

```bash
# 發送訊息至指定 agent
uv run python -m chatpilot.cli.main --agent general-agent --message "你好，請介紹一下你自己"

# 指定 session_id（模擬群組對話）
uv run python -m chatpilot.cli.main --agent general-agent --session "test-session-01" --message "你好"
```

---

## 5. 測試 — E2E 驗收

### 端對端測試（Story 1）

1. 確認伺服器執行中且 LINE webhook 已設定。
2. 從設定路由的群組發送：`你好`
3. 確認 bot 在 10 秒內回覆 agent 的回應。
4. stdout 應顯示：
   ```
   [2026-03-03T12:00:00.000Z] RECV platform=line conversation=C1234567890abcdef text="你好"
   [2026-03-03T12:00:00.001Z] ROUTE keyword="你好" → agent=general-agent
   [2026-03-03T12:00:05.123Z] RESP agent=general-agent text="你好！我是 Copilot Agent..."
   ```

### 靜默測試（Story 3）

從**未設定路由**的群組發送任何訊息，確認：
- Bot 不回覆。
- stdout 顯示 `ROUTE ignored`。
- 無 AI token 消耗。

### 逾時計時器測試

模擬 agent 超過 20 秒：
1. 在 `.env` 設定 `REPLY_TIMEOUT_MS=1000`（1 秒觸發）
2. 發送訊息
3. 確認 1 秒後收到「處理中」通知
4. 確認 agent 完成後，下一則訊息前置補送結果

---

## 6. 新增路由（熱重載）

無需重啟服務，直接編輯 `config/routes.yaml`：

```yaml
routes:
  # 原有路由...

  # 新增：群組 B
  - platform: line
    conversationId: "C0987654321fedcba"
    keywords: []
    fallbackAgent: general-agent
```

儲存檔案後，stdout 立即顯示：
```
[config] Route map reloaded: 2 route(s) from config/routes.yaml
```

---

## 7. 新增 Agent

只需在 `src/chatpilot/agents/` 建立新目錄，實作 `BaseAgent` Protocol：

```python
# src/chatpilot/agents/my_custom_agent/__init__.py
from chatpilot.agents.base import BaseAgent
from chatpilot.core.types import Message, Response
from chatpilot.sdk.session_manager import session_manager


class MyCustomAgent:
    """自訂 agent — 實作 BaseAgent Protocol"""

    @property
    def name(self) -> str:
        return "my-custom-agent"

    async def handle(self, message: Message, session_id: str) -> Response:
        session = await session_manager.resume_session(session_id)
        result = await session_manager.send_and_wait(session, message.text)
        return Response(text=result, attachments=[])


my_custom_agent = MyCustomAgent()
```

然後在 `src/chatpilot/agents/__init__.py` 註冊：
```python
agent_registry["my-custom-agent"] = my_custom_agent
```

最後更新 `config/routes.yaml` 引用新 agent — **無需修改任何 core 程式碼**。

---

## 目錄結構概覽

```
chatpilot/
├── src/chatpilot/
│   ├── core/          # 核心型別（Message, Response, RouteMap）
│   ├── channels/      # Channel adapters（ChannelAdapter Protocol + LINE 實作）
│   ├── dispatch/      # Dispatcher + RouteMap 熱重載
│   ├── agents/        # Agent 實作（BaseAgent Protocol + 範例 agents）
│   ├── sdk/           # Copilot SDK session 管理
│   ├── queue/         # Pending Message Queue
│   ├── server/        # FastAPI webhook server
│   └── cli/           # CLI 工具
├── config/
│   ├── routes.yaml         # 路由設定（可熱重載）
│   └── routes.example.yaml # 範本
├── tests/
│   ├── unit/
│   ├── integration/
│   └── contract/
├── .env.example
└── pyproject.toml
```
