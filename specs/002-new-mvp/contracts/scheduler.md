# Contract: TaskScheduler Protocol

**對應 FR**: FR-013 ~ FR-021a

## Protocol 定義

```python
class TaskScheduler(Protocol):
    """異步任務排程器。管理 task queue 和 runner pool。"""

    async def enqueue(self, task: TaskInfo) -> None:
        """將任務加入 queue。

        Args:
            task: 任務資訊（status 應為 queued）
        Raises:
            QueueFullError: queue 已滿（超過 max_queue_size）
        """
        ...

    async def get_task(self, task_id: str) -> TaskInfo | None:
        """查詢單一任務資訊。"""
        ...

    async def list_tasks(
        self,
        chat_route_id: str | None = None,
        status: TaskStatus | None = None,
        limit: int = 20,
    ) -> list[TaskInfo]:
        """查詢任務清單。

        Args:
            chat_route_id: 過濾特定對話的任務
            status: 過濾特定狀態的任務
            limit: 回傳筆數上限
        Returns:
            按建立時間倒序排列的任務清單
        """
        ...

    async def start(self) -> None:
        """啟動 runner pool，開始消費 queue。"""
        ...

    async def stop(self) -> None:
        """停止 runner pool，等待進行中的任務完成。"""
        ...
```

## TaskStore Protocol

```python
class TaskStore(Protocol):
    """任務持久化儲存。"""

    async def save(self, task: TaskInfo) -> None:
        """儲存或更新任務。"""
        ...

    async def get(self, task_id: str) -> TaskInfo | None:
        """查詢單一任務。"""
        ...

    async def list(
        self,
        chat_route_id: str | None = None,
        status: TaskStatus | None = None,
        limit: int = 20,
    ) -> list[TaskInfo]:
        """查詢任務清單。"""
        ...
```

## Runner Pool 行為

```python
class RunnerPool:
    """並行任務執行池。"""

    def __init__(
        self,
        max_workers: int,         # concurrent_runners from config
        pipeline_executor: PipelineExecutor,
        task_store: TaskStore,
        hub: MessageHub,          # 用於 push 結果
    ): ...

    async def run(self, task: TaskInfo) -> None:
        """執行單一任務。

        流程：
        1. task.status = running, task.started_at = now()
        2. 呼叫 pipeline_executor.execute(task)
        3. 成功 → task.status = completed, 填入 output
        4. 失敗 → task.status = failed, 填入 error
        5. push 結果回原對話（via hub.push）
        6. 儲存 task（via task_store.save）
        """
```

## Task 生命週期

```
enqueue() ──→ [Queue] ──→ runner.run() ──→ completed / failed
                                              │
                                              └─→ hub.push(result)
                                              └─→ task_store.save(task)
```

## 行為約束

- 所有 chatbot 共用一個 queue
- Queue 滿時拒絕新任務（回覆「系統忙碌」）
- Runner pool 大小由 `concurrent_runners` 設定
- Task 完成/失敗後 MUST push 結果回原對話
- Task 完成/失敗後 MUST 持久化到 TaskStore
- MVP 底層為 in-memory queue + SQLite store
- 介面設計允許未來換 Redis / RabbitMQ
