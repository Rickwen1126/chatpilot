# SHIP: Memory Store + Cron Scheduler

tags: [ship, chatpilot, sqlite, cron, memory]

## 1. Problem Statement
**問題**：chatbot 沒有長期記憶和定時執行能力，無法幫使用者記事、提醒、排程
**對象**：LINE/通訊平台上的 chatbot 使用者
**成功條件**：使用者可存取 memo、設定 reminder 到期 push、定期排程觸發 pipeline

## 2. Solution Space
| 做法 | 優勢 | 風險/代價 |
|------|------|-----------|
| SQLite 共用 DB | 零依賴、WAL mode 並行、已有 TaskStore 模式 | 單機限制（但 MVP 不是問題） |
| 分開 DB 檔案 | 隔離性好 | 多連線管理，無必要 |
| Redis/外部 DB | 分散式、高效能 | 外部依賴，MVP 不需要 |

**選擇**：SQLite 共用 `data/chatpilot.db`
**原因**：零新依賴、複用既有 aiosqlite + WAL 模式，MVP 規模足夠

## 3. 技術決策清單
| 決策點 | 選擇 | 原因 | 備選 |
|--------|------|------|------|
| 儲存 | SQLite 共用 DB | 已有模式可複用 | 分開 DB、Redis |
| ID 生成 | uuid4 | 標準 library、與 TaskInfo 一致 | ULID、自增 |
| Cron 格式 | 簡化（daily/weekly/interval） | LLM 容易產生正確格式 | 完整 crontab、自然語言 |
| Scheduler 架構 | CronScheduler 獨立於 RunnerPool | reminder 太輕量不需 pipeline | 共用 RunnerPool |
| 生命週期追蹤 | pending→running→completed/failed | 與 TaskInfo 一致、可查失敗原因 | fire-and-forget |
| Custom prompt 注入 | session rebuild pattern | 複用 broken eviction，無 race | 動態修改 system_message |

## 4. 橫向掃描
| 參考 | 值得借鏡 | 要避開 |
|------|---------|--------|
| ChatGPT Memory | 使用者主動觸發 + LLM 偵測詢問 | 不讓 LLM 自動決定存什麼 |
| Copilot SDK InfiniteSession | system_message 不被壓縮 | 壓縮後 context 丟失（需 custom_prompt 補） |

## 5. 知識風險標記

### [B]lock（不理解，會影響方向）

無。你說「知識好了」，以下確認：

### [R]isky（大概懂但不確定）

- **SQLite WAL mode 並行寫入行為**：CronScheduler tick 和 chatbot tool 同時寫入同一個 DB，WAL 能處理但具體鎖行為不確定
  - Exit Questions:
    1. WAL mode 下兩個 async coroutine 同時 INSERT 不同 table，會互相 block 嗎？ [A]
    2. aiosqlite 的 connection 是 thread-safe 的嗎？還是需要 per-coroutine connection？ [A]

- **Copilot SDK session rebuild 後的對話歷史**：destroy + create 後，之前的對話記錄還在嗎（infinite session workspace）？
  - Exit Questions:
    1. destroy session 後用同一個 session_id create，SDK 會恢復之前的對話嗎？ [B]

- **Cron tick 與 asyncio event loop 的互動**：60 秒 tick 用 asyncio.sleep + while loop，會不會 block event loop？
  - Exit Questions:
    1. asyncio.sleep(60) 期間 event loop 能處理其他 coroutine 嗎？ [A]

### Spike 計畫（B 類 Exit Questions 分群）
- Spike 1: SDK session rebuild 測試 → 覆蓋 R2 Q1
  - 做什麼：用同一個 session_id destroy → create，檢查 get_messages 有沒有歷史
  - 預計時間：10 min

### [N]ice-to-know（不影響方向）
- SQLite VACUUM 時機
- crontab 完整語法
- Pydantic v2 model_validate 的 strict mode

## 6. 開工決策
- [x] 所有 [B]lock 已解除（無 B）
- [x] [B]lock ≤ 3 個
- [x] Problem Statement 清晰
- [x] Solution Space 有比較過
- [x] 技術決策都有根據

**狀態**：可開工（3 個 [R] 開發中驗證，1 個 spike 可選做）
