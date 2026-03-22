"""RunnerPool — concurrent task execution with asyncio.Semaphore."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone

from chatpilot.core.types import NodeOutput, Response, TaskInfo, TaskStatus
from chatpilot.hub.hub import InMemoryMessageHub
from chatpilot.pipeline.executor import PipelineExecutor
from chatpilot.scheduler.store import SqliteTaskStore

logger = logging.getLogger(__name__)


class RunnerPool:
    """Concurrent task execution pool."""

    def __init__(
        self,
        max_workers: int,
        pipeline_executor: PipelineExecutor,
        task_store: SqliteTaskStore,
        hub: InMemoryMessageHub,
        task_timeout: int = 300,
    ) -> None:
        self._semaphore = asyncio.Semaphore(max_workers)
        self._executor = pipeline_executor
        self._store = task_store
        self._hub = hub
        self._task_timeout = task_timeout
        self._running = False
        self._stop_event = asyncio.Event()
        self._tasks: list[asyncio.Task] = []

    async def start(self, scheduler) -> None:
        """Start consuming tasks from the scheduler queue."""
        self._running = True
        self._stop_event.clear()
        self._tasks.append(asyncio.create_task(self._consume(scheduler)))
        logger.info("RunnerPool started")

    async def stop(self) -> None:
        """Stop the runner pool, wait for in-progress tasks."""
        self._running = False
        self._stop_event.set()
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        logger.info("RunnerPool stopped")

    async def _consume(self, scheduler) -> None:
        """Main loop: dequeue tasks and run them."""
        while self._running:
            # Race: either a task arrives or stop signal fires
            dequeue_task = asyncio.ensure_future(scheduler.dequeue())
            stop_task = asyncio.ensure_future(self._stop_event.wait())
            done, pending = await asyncio.wait(
                {dequeue_task, stop_task}, return_when=asyncio.FIRST_COMPLETED
            )
            for p in pending:
                p.cancel()
            if stop_task in done:
                break
            if dequeue_task in done:
                try:
                    task = dequeue_task.result()
                    asyncio.create_task(self._run_with_semaphore(task))
                except asyncio.CancelledError:
                    break
                except Exception:
                    logger.exception("Error in runner pool consumer")

    async def _run_with_semaphore(self, task: TaskInfo) -> None:
        async with self._semaphore:
            await self._run(task)

    async def _run(self, task: TaskInfo) -> None:
        """Execute a single task."""
        task.status = TaskStatus.running
        task.started_at = datetime.now(timezone.utc)
        await self._store.save(task)

        start = time.monotonic()
        try:
            result: NodeOutput = await asyncio.wait_for(
                self._executor.execute(task), timeout=self._task_timeout
            )
            duration_ms = int((time.monotonic() - start) * 1000)

            if result.status == "success":
                task.status = TaskStatus.completed
                task.output_summary = str(result.data)[:200]
                if isinstance(result.data, dict):
                    task.output_full = result.data
                else:
                    task.output_full = {"result": result.data}
            else:
                task.status = TaskStatus.failed
                task.error = result.error or "Pipeline returned error"

            task.duration_ms = duration_ms
            task.completed_at = datetime.now(timezone.utc)

        except Exception as e:
            task.status = TaskStatus.failed
            task.error = str(e)
            task.duration_ms = int((time.monotonic() - start) * 1000)
            task.completed_at = datetime.now(timezone.utc)
            logger.exception(
                "Task %s failed [%s: %s] pipeline=%s duration=%dms",
                task.id[:8],
                type(e).__name__,
                e,
                task.pipeline_name,
                task.duration_ms,
            )

        # Persist — failure here must not block push
        try:
            await self._store.save(task)
        except Exception:
            logger.exception("Failed to persist task %s", task.id[:8])

        # Push result back to chat
        result_text = _format_result(task)
        try:
            await self._hub.push(task.chat_route_id, Response(text=result_text))
        except Exception:
            logger.exception("Failed to push result for task %s", task.id[:8])


def _format_result(task: TaskInfo) -> str:
    """Format task result for push notification."""
    short_id = task.id[:8]
    if task.status == TaskStatus.completed:
        return f"任務完成 (ID: {short_id})\n{task.output_summary}"
    return f"任務失敗 (ID: {short_id})\n{task.error}"
