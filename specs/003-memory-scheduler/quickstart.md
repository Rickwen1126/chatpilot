# Quickstart: Memory Store + Cron Scheduler

---

## 1. 使用 Memo（透過 LINE / CLI）

```
User: 記住：每週五下午 2 點固定開會
Bot: 已記下。

User: 我記了什麼？
Bot: 你有 1 筆記錄：每週五下午 2 點固定開會（3/22 記錄）

User: 刪掉那筆
Bot: 已刪除。
```

## 2. 設定 Reminder

```
User: 提醒我明天下午 3 點開會
Bot: 好的，已設定提醒：2026-03-23 15:00 開會

（隔天 15:00，bot 主動推送）
Bot: 提醒：開會
```

## 3. 設定定期排程

```
User: 每天早上 8 點幫我搜尋台股新聞
Bot: 已排定每日任務：08:00 搜尋台股新聞

（每天 08:00，bot 主動推送結果）
Bot: [搜尋結果]...
```

## 4. 管理排程

```
User: 我有哪些排程？
Bot: 你有 2 個排程：
  1. [reminder] 明天 15:00 開會
  2. [schedule] 每日 08:00 搜尋台股新聞

User: 取消第 2 個
Bot: 已取消。
```

## 5. CLI 測試

```bash
# 測 memo
chatpilot-cli chat "記住：測試 memo 功能"
chatpilot-cli chat "我記了什麼？"

# 測 reminder（設短時間驗證 push）
chatpilot-cli chat "1 分鐘後提醒我測試"
# 等 60 秒看 push 結果
```

## 6. 新增 Memory Type（開發者）

1. 在 `src/chatpilot/memory/types.py` 定義 Pydantic model
2. 在 `SqliteMemoryStore` 新增對應 table 的 CREATE TABLE
3. 如需特殊查詢，在 Protocol 加具名 method
4. 建立對應的 tool（`tools/builtin/`）
5. 在 `server/__init__.py` 註冊 tool
