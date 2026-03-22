# Contract: CronScheduler

**對應 FR**: FR-018 ~ FR-024

## 介面定義

```python
class CronScheduler:
    """定時掃描 Memory Store 中到期的 reminder 和 schedule。"""

    def __init__(
        self,
        memory_store: MemoryStore,
        hub: MessageHub,
        task_scheduler: TaskScheduler,
        tick_interval: int = 60,
    ): ...

    async def start(self) -> None:
        """啟動 tick loop。在 lifespan 中呼叫。"""
        ...

    async def stop(self) -> None:
        """停止 tick loop。等待進行中的 task 完成。"""
        ...
```

## Tick Loop 行為

```
每 tick_interval 秒：
  1. 查詢到期 reminders: memory_store.query_due_before("reminder", now)
  2. 查詢到期 schedules: memory_store.query_due_before("schedule", now)
  3. 對每個到期項目：
     a. 標記 status=running（via memory_store.update）
     b. 執行動作（見下方 Handler）
     c. 成功 → 標記 completed（reminder）或更新 next_run_at + 重設 pending（schedule）
     d. 失敗 → 標記 failed + 記錄 last_error + error log
  4. 掃描 status=failed 項目 → 印 warning log
```

## Handler 行為

### Reminder Handler

```
reminder 到期
  → memory_store.update(status=running)
  → hub.push(route_id, Response(text=f"提醒：{reminder.text}"))
  → 成功 → memory_store.update(status=completed)
  → 失敗 → memory_store.update(status=failed, last_error=str(e))
```

### Schedule Handler

```
schedule 到期
  → memory_store.update(status=running)
  → task_scheduler.enqueue(TaskInfo(...))  ← 複用既有 pipeline 執行
  → enqueue 成功 → 計算 next_run_at → memory_store.update(status=pending, next_run_at=...)
  → enqueue 失敗 → memory_store.update(status=failed, last_error=str(e))
```

**注意**：schedule 的「完成」只是 enqueue 成功，不是 pipeline 執行完成。
Pipeline 結果由 RunnerPool push 回對話（既有流程）。

## Cron 表達式解析

| 格式 | 範例 | next_run_at 計算 |
|------|------|-----------------|
| `daily HH:MM` | `daily 08:00` | 今天或明天的 HH:MM UTC |
| `weekly DAY HH:MM` | `weekly mon 09:00` | 下個 DAY 的 HH:MM UTC |
| `interval Nm` | `interval 30m` | now + N minutes |
| `interval Nh` | `interval 2h` | now + N hours |

## 行為約束

- tick loop MUST 在 lifespan 啟動，server 關閉時 MUST 停止
- 每個到期項目 MUST 先標記 running 再執行（防止重複觸發）
- push 失敗 MUST 記錄 last_error，不自動 retry
- status=failed 的項目每次 scan MUST 印 warning log
- CronScheduler MUST NOT 直接 import adapter（透過 hub.push）
