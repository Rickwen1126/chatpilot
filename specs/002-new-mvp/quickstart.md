# Quickstart: Agent Gateway MVP v2

**前置需求**：Python 3.11+, [uv](https://docs.astral.sh/uv/), GitHub Copilot 訂閱

---

## 1. 安裝

```bash
cd chatpilot
uv sync
```

## 2. 設定環境變數

```bash
cp .env.example .env
# 編輯 .env，填入以下必要設定：
```

| 變數 | 說明 | 取得方式 |
|------|------|----------|
| `LINE_CHANNEL_SECRET` | LINE channel secret | LINE Developers Console |
| `LINE_CHANNEL_ACCESS_TOKEN` | LINE channel access token | Messaging API tab → Issue |
| `PORT` | Server port | 預設 2999 |

## 3. 設定路由

編輯 `config/routes.yaml`：

```yaml
match_weights:
  group_id: 10
  user_id: 8
  platform: 5

bindings:
  - match: { platform: "line" }
    chatbot: general-bot
  - chatbot: general-bot          # default

chatbots:
  general-bot:
    model: gpt-4.1
    system_message: "你是一個通用助手。"
    tools: []
    context_window: 20

agents: {}

scheduler:
  concurrent_runners: 2
  max_queue_size: 100
```

## 4. 啟動 Server

```bash
uv run uvicorn chatpilot.server.app:create_app --factory --host 0.0.0.0 --port 2999
```

## 5. 暴露 Webhook（本地開發）

```bash
cloudflared tunnel run --url http://localhost:2999
```

在 LINE Developers Console 設定 Webhook URL：
`https://your-tunnel-domain/webhook/line`

## 6. 測試

### Mock Adapter 本地測試

```bash
# 透過 mock adapter 測試 chatbot
curl -X POST http://localhost:2999/webhook/mock \
  -H "Content-Type: application/json" \
  -d '{"text": "你好", "user_id": "test-user"}'
```

### CLI 測試（P2）

```bash
# 直接與 chatbot 對話
uv run chatpilot-cli --chatbot general-bot --message "你好"

# 觸發 pipeline
uv run chatpilot-cli --pipeline inventory-report --input '{"query": "查庫存"}'
```

### 單元測試

```bash
uv run pytest
uv run ruff check src/
```

## 7. 目錄結構

```
chatpilot/
├── src/chatpilot/         # 原始碼
│   ├── core/              # 型別、錯誤、設定
│   ├── hub/               # Message Hub
│   ├── routing/           # Binding Router
│   ├── chatbot/           # Chatbot Session
│   ├── tools/             # Tool Factory
│   ├── scheduler/         # Task Scheduler
│   ├── pipeline/          # Pipeline 框架
│   ├── adapters/          # Channel Adapters
│   ├── agents/            # Pipeline Agent 定義
│   ├── sdk/               # SDK 輔助
│   ├── cli/               # CLI 工具
│   └── server/            # FastAPI App
├── tests/                 # 測試
├── config/                # 設定檔
├── data/                  # 執行時資料（tasks.db, memory/, context/）
└── specs/                 # 設計文件
```

## 8. 開發流程

1. **新增 tool**：在 `src/chatpilot/tools/builtin/` 新增模組，
   在 app 初始化時向 ToolFactory 註冊
2. **新增 pipeline**：在 `src/chatpilot/pipeline/` 新增 pipeline class，
   定義 node chain
3. **新增 adapter**：實作 `ChannelAdapter` Protocol，
   在 app 初始化時註冊
4. **修改路由**：編輯 `config/routes.yaml`，server 自動熱重載
