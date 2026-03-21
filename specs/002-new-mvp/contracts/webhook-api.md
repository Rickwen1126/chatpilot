# Contract: Webhook HTTP API

**對應 FR**: FR-006, FR-007

## Endpoints

### POST /webhook/{platform}

接收平台 webhook 事件。

**Path Parameters**:
- `platform` (string): 平台標識（`line`, `mock`）

**Request**:
- Headers: 平台專屬簽章 header（如 LINE 的 `X-Line-Signature`）
- Body: 平台原始 webhook payload

**Response**:

| 狀態碼 | 說明 |
|--------|------|
| 200 | 成功接收（不代表已處理完成） |
| 400 | 請求格式錯誤 |
| 401 | 簽章驗證失敗 |
| 404 | 未知平台 |

**處理流程**:
```
1. 找到對應 adapter（by platform）
2. adapter.verify_request()
3. adapter.parse_messages() → Message[]
4. 每個 Message → hub.receive(message, adapter)
5. 回傳 200（非阻塞，處理在背景進行）
```

**非阻塞要求**：Webhook handler MUST 快速回傳 200，
不等待 chatbot 處理完成。chatbot 回覆透過 adapter.send_reply() 非同步送出。

### GET /health

健康檢查。

**Response**:

```json
{
  "status": "ok",
  "version": "0.2.0",
  "uptime_seconds": 1234
}
```

### POST /cli/chat

CLI 直接對話（P2，開發用）。

**Request Body**:
```json
{
  "chatbot": "general-bot",
  "message": "你好",
  "session_id": "optional-session-id"
}
```

**Response**:
```json
{
  "response": "你好！有什麼我可以幫你的嗎？",
  "session_id": "abc123"
}
```

### POST /cli/task

CLI 觸發 pipeline（P2，開發用）。

**Request Body**:
```json
{
  "pipeline": "inventory-report",
  "input": { "query": "查庫存" }
}
```

**Response**:
```json
{
  "task_id": "a1b2c3d4-...",
  "status": "queued"
}
```

## 錯誤格式

```json
{
  "error": "friendly error message",
  "code": "ERROR_CODE"
}
```

| Code | 說明 |
|------|------|
| `SIGNATURE_INVALID` | 簽章驗證失敗 |
| `PLATFORM_UNKNOWN` | 未知平台 |
| `CHATBOT_NOT_FOUND` | 對應 chatbot 不存在 |
| `QUEUE_FULL` | 任務隊列已滿 |
| `INTERNAL_ERROR` | 系統內部錯誤 |
