"""TaskStore — SQLite WAL mode persistence for task history."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

import aiosqlite

from chatpilot.core.types import TaskInfo, TaskStatus

logger = logging.getLogger(__name__)

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS tasks (
    id          TEXT PRIMARY KEY,
    status      TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    started_at  TEXT,
    completed_at TEXT,
    duration_ms INTEGER,
    input_summary  TEXT,
    output_summary TEXT,
    output_full    TEXT,
    chat_route_id  TEXT NOT NULL,
    pipeline_name  TEXT NOT NULL,
    error          TEXT,
    input_data     TEXT DEFAULT '{}',
    reply_mode     TEXT DEFAULT 'direct'
);
"""

CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);",
    "CREATE INDEX IF NOT EXISTS idx_tasks_chat_route ON tasks(chat_route_id);",
]


class SqliteTaskStore:
    """SQLite-backed task store with WAL mode."""

    def __init__(self, db_path: str = "data/tasks.db") -> None:
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def initialize(self) -> None:
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self._db_path)
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute(CREATE_TABLE)
        for idx in CREATE_INDEXES:
            await self._db.execute(idx)
        await self._migrate()
        await self._db.commit()
        logger.info("TaskStore initialized at %s", self._db_path)

    async def _migrate(self) -> None:
        """Add new columns to existing databases."""
        if self._db is None:
            return
        async with self._db.execute("PRAGMA table_info(tasks)") as cursor:
            cols = [row[1] for row in await cursor.fetchall()]
        if "input_data" not in cols:
            await self._db.execute(
                "ALTER TABLE tasks ADD COLUMN input_data TEXT DEFAULT '{}'"
            )
            logger.info("Migrated tasks: added input_data column")
        if "reply_mode" not in cols:
            await self._db.execute(
                "ALTER TABLE tasks ADD COLUMN reply_mode TEXT DEFAULT 'direct'"
            )
            logger.info("Migrated tasks: added reply_mode column")

    async def close(self) -> None:
        if self._db:
            await self._db.close()

    async def save(self, task: TaskInfo) -> None:
        if self._db is None:
            raise RuntimeError("TaskStore not initialized")
        await self._db.execute(
            """INSERT OR REPLACE INTO tasks
               (id, status, created_at, started_at, completed_at, duration_ms,
                input_summary, output_summary, output_full, chat_route_id,
                pipeline_name, error, input_data, reply_mode)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                task.id,
                task.status.value,
                task.created_at.isoformat(),
                task.started_at.isoformat() if task.started_at else None,
                task.completed_at.isoformat() if task.completed_at else None,
                task.duration_ms,
                task.input_summary,
                task.output_summary,
                json.dumps(task.output_full) if task.output_full else None,
                task.chat_route_id,
                task.pipeline_name,
                task.error,
                json.dumps(task.input_data) if task.input_data else "{}",
                task.reply_mode,
            ),
        )
        await self._db.commit()

    async def get(self, task_id: str) -> TaskInfo | None:
        if self._db is None:
            raise RuntimeError("TaskStore not initialized")
        async with self._db.execute(
            "SELECT * FROM tasks WHERE id = ?", (task_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row is None:
                return None
            return _row_to_task(row)

    async def list(
        self,
        chat_route_id: str | None = None,
        status: TaskStatus | None = None,
        limit: int = 20,
    ) -> list[TaskInfo]:
        if self._db is None:
            raise RuntimeError("TaskStore not initialized")
        conditions = []
        params: list = []
        if chat_route_id:
            conditions.append("chat_route_id = ?")
            params.append(chat_route_id)
        if status:
            conditions.append("status = ?")
            params.append(status.value)
        where = " AND ".join(conditions) if conditions else "1=1"
        query = f"SELECT * FROM tasks WHERE {where} ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        async with self._db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [_row_to_task(row) for row in rows]


def _row_to_task(row: tuple) -> TaskInfo:
    return TaskInfo(
        id=row[0],
        status=TaskStatus(row[1]),
        created_at=datetime.fromisoformat(row[2]),
        started_at=datetime.fromisoformat(row[3]) if row[3] else None,
        completed_at=datetime.fromisoformat(row[4]) if row[4] else None,
        duration_ms=row[5],
        input_summary=row[6] or "",
        output_summary=row[7],
        output_full=json.loads(row[8]) if row[8] else None,
        chat_route_id=row[9],
        pipeline_name=row[10],
        error=row[11],
        input_data=json.loads(row[12]) if len(row) > 12 and row[12] else {},
        reply_mode=row[13] if len(row) > 13 and row[13] else "direct",
    )
