# Research: Memory Store + Cron Scheduler

**Date**: 2026-03-22
**Spec**: [spec.md](spec.md)

---

## R-001：SQLite 單 DB 還是分開

**Decision**: 共用 `data/chatpilot.db`，分 table

Memory Store 和既有 TaskStore 共用同一個 SQLite 檔案，各自 table：
- `memory_memos` — memo type
- `memory_reminders` — reminder type
- `memory_schedules` — schedule type
- `tasks` — 既有 TaskStore

**Rationale**: 單一 SQLite 檔案 + WAL mode 已夠用。分開 DB 檔案增加管理複雜度無好處。
table 前綴 `memory_` 避免名稱衝突。

**Alternatives considered**:
- 分開 DB 檔案（`data/memory.db`）→ 多一個連線管理，無必要
- 單一 `memory` table 存所有 type（用 type column 區分）→ schema 不一致，查詢效能差

---

## R-002：Memory Store 的 ID 生成策略

**Decision**: `uuid.uuid4()`，與 TaskInfo 一致

- 標準 library，無外部依賴
- 碰撞機率可忽略
- 對使用者顯示時截取前 8 字元

**Alternatives considered**:
- 自增 ID → SQLite auto-increment 可用但 ID 可預測
- ULID → 需額外依賴

---

## R-003：簡化 Cron 表達式格式

**Decision**: 三種格式，不支援完整 crontab

| 格式 | 範例 | 說明 |
|------|------|------|
| `daily HH:MM` | `daily 08:00` | 每天指定時間 |
| `weekly DAY HH:MM` | `weekly mon 09:00` | 每週指定日指定時間 |
| `interval Nm` 或 `interval Nh` | `interval 30m` / `interval 2h` | 每 N 分鐘 / 小時 |

- DAY 支援：mon, tue, wed, thu, fri, sat, sun
- 時間為 UTC
- `next_run_at` 在建立時和每次完成後計算

**Rationale**: 完整 crontab 語法對 LLM 來說不直觀，簡化格式讓 LLM 更容易產生正確的表達式。
使用者說「每天早上 8 點」→ LLM 轉為 `daily 08:00`。

**Alternatives considered**:
- 完整 crontab（`0 8 * * *`）→ LLM 產生容易出錯，使用者看不懂
- 自然語言存取 → 解析不穩定，不如讓 LLM 轉格式

---

## R-004：Cron Scheduler 與既有 RunnerPool 的關係

**Decision**: 分離。CronScheduler 獨立 tick loop，不共用 RunnerPool

- CronScheduler 自己跑 tick loop（60s interval）
- Reminder 到期 → 直接呼叫 `hub.push()`（輕量，不需 pipeline）
- Schedule 到期 → 呼叫既有 `scheduler.enqueue()`（觸發 pipeline，由 RunnerPool 執行）

**Rationale**: CronScheduler 的職責是「掃描 + 觸發」，不是「執行」。
執行 pipeline 複用既有 RunnerPool，不重建。
Reminder 的 push 太輕量，不需要經過 queue。

**Alternatives considered**:
- CronScheduler 共用 RunnerPool → reminder push 不需要 pipeline，繞路
- CronScheduler 自己管 worker → 跟 RunnerPool 職責重疊

---

## R-005：route_id 推導邏輯

**Decision**: 從 `invocation["session_id"]` 反推

tool 被呼叫時，`ToolInvocation` 帶有 `session_id`。
我們的 session_id 格式是 `{platform}-{conversation_id}`（SDK 不接受冒號）。

但 Memory Store 的 route_id 格式是 `{platform}:{conversation_id}`（冒號分隔）。

需要一個轉換：`session_id.replace("-", ":", 1)` → route_id。

**注意**：conversation_id 本身可能含有 `-`，所以只替換第一個。

---

## R-006：Cron Scheduler 失敗項目的處理

**Decision**: 不自動 retry，只 log + 保留 failed 狀態

- status=failed 的項目保留在 Memory Store
- 每次 scan 遇到 failed → 印 warning log
- 開發者可手動查看 + 重設 status=pending 來重試
- 使用者可透過 `list_schedules` tool 看到失敗的排程

**Rationale**: MVP 自動 retry 增加複雜度（retry 幾次？backoff？），
且失敗原因通常是配置問題（pipeline 不存在、adapter 壞掉），
自動 retry 不會解決。

---

## 未解決項目

無。所有待決事項已解決。
