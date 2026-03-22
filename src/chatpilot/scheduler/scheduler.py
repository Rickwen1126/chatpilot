"""InMemoryTaskScheduler — asyncio.Queue-based task scheduler."""

from __future__ import annotations

import asyncio
import logging

from chatpilot.core.errors import QueueFullError
from chatpilot.core.types import TaskInfo, TaskStatus
from chatpilot.scheduler.store import SqliteTaskStore

logger = logging.getLogger(__name__)


class InMemoryTaskScheduler:
    """In-memory task scheduler with asyncio.Queue."""

    def __init__(
        self,
        store: SqliteTaskStore,
        max_queue_size: int = 100,
    ) -> None:
        self._store = store
        self._queue: asyncio.Queue[TaskInfo] = asyncio.Queue(maxsize=max_queue_size)
        self._max_queue_size = max_queue_size

    async def enqueue(self, task: TaskInfo) -> None:
        """Add a task to the queue."""
        if self._queue.qsize() >= self._max_queue_size:
            raise QueueFullError()
        task.status = TaskStatus.queued
        await self._store.save(task)
        await self._queue.put(task)
        logger.info("Task %s enqueued (pipeline=%s)", task.id[:8], task.pipeline_name)

    async def dequeue(self) -> TaskInfo:
        """Get next task from queue (blocks until available)."""
        return await self._queue.get()

    async def get_task(self, task_id: str) -> TaskInfo | None:
        return await self._store.get(task_id)

    async def list_tasks(
        self,
        chat_route_id: str | None = None,
        status: TaskStatus | None = None,
        limit: int = 20,
    ) -> list[TaskInfo]:
        return await self._store.list(chat_route_id, status, limit)
