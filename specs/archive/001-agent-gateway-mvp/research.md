# Phase 0 研究報告：通用 Agent Gateway MVP

**Branch**: `001-agent-gateway-mvp` | **Date**: 2026-03-03 | **Updated**: 2026-03-03 (TS→Python)

## 研究議題一：語言與框架選擇

### 決策：Python 3.11+ / uv

**根據**：
- Copilot SDK（`github-copilot-sdk`）提供官方 Python SDK，async/await 原生，Pydantic tool 定義。
- LINE Messaging API SDK（`line-bot-sdk`）官方 Python 版，支援 async webhook handler。
- 未來需整合 PyAV（音視頻處理）、Cython（C 擴展）、C 函式庫——Python 是唯一自然選擇。
- Pydantic v2 提供比 Zod 更強的 schema 驗證與 IDE 支援，與 FastAPI 深度整合。
- `uv` 作為套件管理器，比 pip/poetry 快 10-100x，現代 Rust-based 工具。

**評估的替代方案**：
- TypeScript（`@github/copilot-sdk`）：SDK 文件略多，但無 PyAV/Cython/C 生態；若未來需要音視頻處理必須跨語言呼叫。
- Go（`github.com/github/copilot-sdk/go`）：官方 README 明確指出缺乏 higher-level abstractions；LINE Go SDK 社群資源少。
- .NET（`GitHub.Copilot.SDK`）：文件最不完整。

**結論**：Python 為長期最佳選擇——兼顧 Copilot SDK 支援度與 PyAV/C 擴展生態。

---

## 研究議題二：Web Framework

### 決策：FastAPI + uvicorn

**根據**：
- Python async-native web framework，效能在 Python 生態中最佳。
- Pydantic v2 request/response 驗證內建（無需額外 middleware）。
- 原生 async/await，`async def` endpoint 直接支援非同步 IO。
- `line-bot-sdk` Python 版提供 `AsyncWebhookHandler`，與 FastAPI 完美整合。
- uvicorn ASGI server 提供生產級效能。

**評估的替代方案**：
- Flask：同步為主，async 支援較弱；需額外 WSGI worker。
- Django：過重，MVC 架構不適合 webhook-only 服務。
- Starlette：FastAPI 底層，可直接使用但缺少自動 API 文件與 Pydantic 整合糖衣。

---

## 研究議題三：GitHub Copilot SDK — Session API

### 決策：`CopilotClient` + event-based session 模式

**具體 API**（Python）：
```python
import asyncio
from copilot import CopilotClient

client = CopilotClient()
await client.start()

# 建立 session（以 platform-conversation_id 為識別碼）
session = await client.create_session({
    "model": "gpt-4.1",
    "session_id": "line-C1234567890abcdef"
})

# 事件驅動：監聽 agent 回應
done = asyncio.Event()
result_text = ""

def on_event(event):
    nonlocal result_text
    if event.type.value == "assistant.message":
        result_text = event.data.content
    elif event.type.value == "session.idle":
        done.set()

session.on(on_event)
await session.send({"prompt": "使用者訊息"})
await done.wait()
```

**與 TypeScript SDK 差異**：
- Python SDK 使用 event callback 模式（`session.on(handler)`），而非 TypeScript 的 `sendAndWait()`。
- 需自行包裝 `send_and_wait()` helper 以簡化使用。
- Session state 同樣自動持久化、compaction 自動管理。

**Session 持久化機制**：
- SDK 自動將 session 狀態存至 workspace directory。
- 支援 `get_messages()` 取得對話歷史。
- Compaction 事件：`session.compaction_start`、`session.compaction_complete`。

**sessionId 命名規則**（本專案）：
```
session_id = "{platform}-{conversation_id}"
# 例：line-C1234567890abcdef（群組）
#     line-U1234567890abcdef（私聊，使用 userId）
```

---

## 研究議題四：LINE Reply Token TTL

### 決策：以 60 秒為設計上限，20 秒逾時計時器提供充裕安全邊際

**關鍵事實**：
- LINE 官方文件明確規定：reply token 必須在 **webhook 收到後 1 分鐘（60 秒）內** 使用。
- Reply token 為**一次性**：同一 token 只能呼叫一次 Reply API；不論是過期或已用過，API 均回傳 HTTP 400 `"Invalid reply token"`。
- LINE webhook server 要求 bot 端在 **~2 秒內** 回覆 HTTP 200 OK，否則 LINE 會重試送達。

**架構影響**：
```
webhook 到達
    ├── 立即回覆 HTTP 200 OK（<2秒）
    ├── 啟動 20 秒逾時計時器
    └── 非同步處理 agent
         ├── 完成（<20秒）→ 使用 reply token 回覆
         └── 計時器觸發（>20秒）→ 用 reply token 回覆「處理中」ACK
                                 → agent 結果暫存 Pending Queue
                                 → 等待下一則訊息攜帶新 reply token 補送
```

20 秒計時器設計合理：觸發時距 60 秒上限尚有 40 秒安全邊際。

---

## 研究議題五：`routes.yaml` 熱重載機制

### 決策：`watchdog` + `pyyaml`

**套件選擇**：
- `watchdog`（Python 標準 file system monitoring，跨平台）
- `pyyaml`（YAML 1.1 解析，最廣泛使用）

**關鍵實作**：
```python
from watchdog.observers import Observer
from watchdog.events import FileModifiedEvent, FileSystemEventHandler

class RouteFileHandler(FileSystemEventHandler):
    def on_modified(self, event: FileModifiedEvent):
        if event.src_path.endswith("routes.yaml"):
            # 延遲 200ms 避免讀取到部分寫入的檔案
            asyncio.get_event_loop().call_later(0.2, self._reload)

    def _reload(self):
        try:
            new_map = load_routes(self.path)
            self.on_change(new_map)
        except Exception as e:
            logger.error(f"Route reload failed: {e}")
            # 保留舊設定，不崩潰
```

**安全邊際設計**：
- 200ms debounce 防止讀取到部分寫入的 YAML。
- 支援 vim/VS Code 的 atomic rename 寫入。
- YAML 解析失敗時保留舊設定，記錄錯誤至 stderr（不崩潰）。
- 設定更新為 Python atomic assignment（`self._route_map = new_map`），無 race condition。

---

## 研究議題六：Pending Message Queue 設計

### 決策：in-memory `dict[str, list[PendingMessage]]`

**設計**：
```python
from chatpilot.core.types import PendingMessage

# key: session_id ("line-{conversation_id}")
# value: 待補送的 PendingMessage 列表（通常只有 1 筆）
pending_queue: dict[str, list[PendingMessage]] = {}
```

**補送時機**：下一則來自相同 session_id 的訊息到達時，優先補送所有 pending response，再處理新訊息。

**MVP 限制**：in-memory，process 重啟後 queue 遺失（可接受）。

---

## 套件清單

| 套件 | 版本 | 用途 |
|------|------|------|
| `github-copilot-sdk` | 0.1.0 | Copilot SDK agent 執行引擎 |
| `line-bot-sdk` | latest | LINE Messaging API |
| `fastapi` | latest | ASGI webhook server |
| `uvicorn` | latest | ASGI server |
| `pydantic` | v2 | Schema 驗證、資料模型 |
| `watchdog` | latest | routes.yaml 熱重載 |
| `pyyaml` | latest | YAML 解析 |
| `python-dotenv` | latest | `.env` 環境變數載入 |

**開發依賴**：

| 套件 | 版本 | 用途 |
|------|------|------|
| `pytest` | latest | 測試框架 |
| `pytest-asyncio` | latest | async 測試支援 |
| `httpx` | latest | FastAPI TestClient |
| `ruff` | latest | Linter + formatter |
