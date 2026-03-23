# Data Model: Memory Store + Cron Scheduler

**Date**: 2026-03-22
**Spec**: [spec.md](spec.md) | **Research**: [research.md](research.md)

---

## 核心實體

### Memo（泛用記憶）

| 欄位 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `id` | `str` | Y | UUID |
| `route_id` | `str` | Y | 對話路由 ID |
| `text` | `str` | Y | 記憶內容 |
| `tags` | `list[str]` | N | 標籤（預設空） |
| `created_at` | `datetime` | Y | 建立時間（UTC） |

### Custom Prompt（使用者偏好）

| 欄位 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `id` | `str` | Y | UUID |
| `route_id` | `str` | Y | 對話路由 ID |
| `text` | `str` | Y | 偏好描述 |
| `category` | `str` | N | 分類（tone/format/method/general，預設 general） |
| `created_at` | `datetime` | Y | 建立時間（UTC） |

**注入方式**：session 建立時，從 Memory Store 讀取該 route 所有 custom_prompt，合併到 system_message 尾端。

### Reminder（一次性提醒）

| 欄位 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `id` | `str` | Y | UUID |
| `route_id` | `str` | Y | 對話路由 ID |
| `text` | `str` | Y | 提醒內容 |
| `due_at` | `datetime` | Y | 到期時間（UTC） |
| `status` | `MemoryStatus` | Y | pending / running / completed / failed |
| `last_error` | `str \| None` | N | 最近一次失敗原因 |
| `created_at` | `datetime` | Y | 建立時間（UTC） |

**狀態轉換**：
```
pending → running → completed
                  → failed
```

- `pending`：等待到期
- `running`：CronScheduler 正在執行 push
- `completed`：已成功 push，不再被 scan
- `failed`：push 失敗，保留供查看

### Schedule（重複排程）

| 欄位 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `id` | `str` | Y | UUID |
| `route_id` | `str` | Y | 對話路由 ID |
| `cron_expr` | `str` | Y | 簡化 cron 表達式 |
| `pipeline_name` | `str` | Y | 要觸發的 pipeline |
| `input_data` | `dict` | Y | pipeline 輸入參數 |
| `status` | `MemoryStatus` | Y | pending / running / completed / failed |
| `last_run_at` | `datetime \| None` | N | 上次執行時間 |
| `next_run_at` | `datetime` | Y | 下次執行時間（UTC） |
| `last_error` | `str \| None` | N | 最近一次失敗原因 |
| `created_at` | `datetime` | Y | 建立時間（UTC） |

**狀態轉換**（重複）：
```
pending → running → completed → pending (next_run_at 更新)
                  → failed (保留，下次 scan log warning)
```

### MemoryStatus（共用狀態 Enum）

| 值 | 說明 |
|-----|------|
| `pending` | 等待處理 |
| `running` | 正在執行 |
| `completed` | 已完成 |
| `failed` | 執行失敗 |

---

## 持久化

### SQLite Tables（共用 `data/chatpilot.db`）

```sql
CREATE TABLE memory_memos (
    id          TEXT PRIMARY KEY,
    route_id    TEXT NOT NULL,
    text        TEXT NOT NULL,
    tags        TEXT DEFAULT '[]',    -- JSON array
    created_at  TEXT NOT NULL         -- ISO 8601
);

CREATE INDEX idx_memos_route ON memory_memos(route_id);

CREATE TABLE memory_custom_prompts (
    id          TEXT PRIMARY KEY,
    route_id    TEXT NOT NULL,
    text        TEXT NOT NULL,
    category    TEXT DEFAULT 'general',
    created_at  TEXT NOT NULL
);

CREATE INDEX idx_custom_prompts_route ON memory_custom_prompts(route_id);

CREATE TABLE memory_reminders (
    id          TEXT PRIMARY KEY,
    route_id    TEXT NOT NULL,
    text        TEXT NOT NULL,
    due_at      TEXT NOT NULL,        -- ISO 8601
    status      TEXT NOT NULL DEFAULT 'pending',
    last_error  TEXT,
    created_at  TEXT NOT NULL
);

CREATE INDEX idx_reminders_route ON memory_reminders(route_id);
CREATE INDEX idx_reminders_status_due ON memory_reminders(status, due_at);

CREATE TABLE memory_schedules (
    id             TEXT PRIMARY KEY,
    route_id       TEXT NOT NULL,
    cron_expr      TEXT NOT NULL,
    pipeline_name  TEXT NOT NULL,
    input_data     TEXT NOT NULL,     -- JSON object
    status         TEXT NOT NULL DEFAULT 'pending',
    last_run_at    TEXT,
    next_run_at    TEXT NOT NULL,
    last_error     TEXT,
    created_at     TEXT NOT NULL
);

CREATE INDEX idx_schedules_route ON memory_schedules(route_id);
CREATE INDEX idx_schedules_status_next ON memory_schedules(status, next_run_at);
```

### 查詢索引設計

- `idx_reminders_status_due`：CronScheduler 掃描用，`WHERE status='pending' AND due_at <= ?`
- `idx_schedules_status_next`：CronScheduler 掃描用，`WHERE status='pending' AND next_run_at <= ?`
- `idx_*_route`：per-route list 查詢用
