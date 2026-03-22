"""TaskScheduler and TaskStore Protocols."""

from __future__ import annotations

from typing import Protocol

from chatpilot.core.types import TaskInfo, TaskStatus


class TaskStore(Protocol):
    """Task persistence interface."""

    async def save(self, task: TaskInfo) -> None: ...
    async def get(self, task_id: str) -> TaskInfo | None: ...
    async def list(
        self,
        chat_route_id: str | None = None,
        status: TaskStatus | None = None,
        limit: int = 20,
    ) -> list[TaskInfo]: ...


class TaskScheduler(Protocol):
    """Async task scheduler interface."""

    async def enqueue(self, task: TaskInfo) -> None: ...
    async def get_task(self, task_id: str) -> TaskInfo | None: ...
    async def list_tasks(
        self,
        chat_route_id: str | None = None,
        status: TaskStatus | None = None,
        limit: int = 20,
    ) -> list[TaskInfo]: ...
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
