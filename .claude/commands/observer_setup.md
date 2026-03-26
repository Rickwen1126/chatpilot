---
description: 設定觀察者模式。Triggers on /observer_setup, "設定觀察者", "新增觀察者".
---

## Observer Setup

設定群組觀察者（靜默收集 + 定期整理 + 跨 chat 查詢）。

### 1. 確認目標群組

```bash
curl -s http://localhost:2999/cli/routes | python3 -c "
import sys, json
for r in json.load(sys.stdin)['routes']:
    if r['platform'] == 'line':
        print(f'{r.get(\"label\",\"?\"):24} | {r[\"route_id\"]} | {r[\"current_chatbot\"]}')"
```

### 2. 建立 Observer Chatbot（routes.yaml）

```yaml
chatbots:
  {name}-observer:
    model: gpt-5-mini                    # 整理用，不需要最強
    system_message: "{描述}觀察者。"
    tools: []                            # observer 不需要 tool
    observer_mode: true
    observer_batch_size: 10              # 幾則觸發一次整理
    observer_categories: [請假, 進料, 出料, 出貨, 工程進度]  # 分類提示
    observer_allowed_consumers: ["line:Ufc68..."]  # 誰能查
```

### 3. 設定 Binding

```yaml
bindings:
  - match: { group_id: "{GROUP_ID}" }
    chatbot: {name}-observer
```

### 4. 設定查詢端 Chatbot

查詢端 chatbot 的 tools 加入 `query_observations`：

```yaml
  admin-bot:
    model: gpt-5.2
    tools: [..., query_observations, ...]
```

### 5. 重啟 + 驗證

```bash
# 重啟 server
lsof -ti:2999 | xargs kill -9; sleep 1
uv run uvicorn chatpilot.server:create_app --factory --host 0.0.0.0 --port 2999 &

# 確認 observer 註冊
grep "Observer registered" /tmp/chatpilot.log

# 確認 routes
curl -s http://localhost:2999/cli/routes | python3 -c "..."
```

### 6. 測試

```bash
# 發送測試訊息（mock）
for i in $(seq 1 BATCH_SIZE); do
  curl -s -X POST http://localhost:2999/webhook/mock \
    -H "Content-Type: application/json" \
    -d "{\"text\": \"測試訊息 $i\", \"user_id\": \"u$i\", \"group_id\": \"{GROUP_ID}\", \"is_mention\": false}"
  sleep 0.3
done

# 看 log 確認 batch 觸發
grep "[observer]" /tmp/chatpilot.log

# 查詢觀察資料
curl -s -X POST http://localhost:2999/cli/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "查詢 {OBSERVER_NAME} 的觀察紀錄", "user_id": "test"}'
```

### Key Config

| 欄位 | 說明 |
|------|------|
| `observer_mode: true` | 靜默模式，不回話 |
| `observer_batch_size` | 幾則觸發整理（需 ≤ context_window，自動 max） |
| `observer_categories` | LLM 分類提示 |
| `observer_allowed_consumers` | 哪些 route_id 能查（空 = 全開） |
| `model` | 整理用 model（gpt-5-mini 夠用） |

### 注意

- Observer 優先於 @mention — observer route 裡的所有訊息都靜默收集
- batch_size 達標才觸發，之間不會有任何回應
- context_window 自動設為 max(context_window, batch_size)
- 觀察資料存在 memory_observations table，可用 query_observations tool 跨 chat 查
