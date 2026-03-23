"""SqliteMemoryStore — SQLite-backed memory store implementation."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite

from chatpilot.memory.types import (
    CustomPrompt,
    Memo,
    MemoryStatus,
    Reminder,
    Schedule,
)

logger = logging.getLogger(__name__)

# Type → (table_name, pydantic_model, time_field_for_due_query)
TYPE_REGISTRY: dict[str, tuple[type, str, str | None]] = {
    "memo": (Memo, "memory_memos", None),
    "custom_prompt": (CustomPrompt, "memory_custom_prompts", None),
    "reminder": (Reminder, "memory_reminders", "due_at"),
    "schedule": (Schedule, "memory_schedules", "next_run_at"),
}

CREATE_TABLES = """
CREATE TABLE IF NOT EXISTS memory_memos (
    id          TEXT PRIMARY KEY,
    route_id    TEXT NOT NULL,
    text        TEXT NOT NULL,
    tags        TEXT DEFAULT '[]',
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_memos_route ON memory_memos(route_id);

CREATE TABLE IF NOT EXISTS memory_custom_prompts (
    id          TEXT PRIMARY KEY,
    route_id    TEXT NOT NULL,
    text        TEXT NOT NULL,
    category    TEXT DEFAULT 'general',
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_custom_prompts_route
    ON memory_custom_prompts(route_id);

CREATE TABLE IF NOT EXISTS memory_reminders (
    id          TEXT PRIMARY KEY,
    route_id    TEXT NOT NULL,
    text        TEXT NOT NULL,
    due_at      TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'pending',
    last_error  TEXT,
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_reminders_route ON memory_reminders(route_id);
CREATE INDEX IF NOT EXISTS idx_reminders_status_due
    ON memory_reminders(status, due_at);

CREATE TABLE IF NOT EXISTS memory_schedules (
    id             TEXT PRIMARY KEY,
    route_id       TEXT NOT NULL,
    cron_expr      TEXT NOT NULL,
    pipeline_name  TEXT NOT NULL,
    input_data     TEXT NOT NULL DEFAULT '{}',
    status         TEXT NOT NULL DEFAULT 'pending',
    last_run_at    TEXT,
    next_run_at    TEXT NOT NULL,
    last_error     TEXT,
    created_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_schedules_route ON memory_schedules(route_id);
CREATE INDEX IF NOT EXISTS idx_schedules_status_next
    ON memory_schedules(status, next_run_at);
"""


class SqliteMemoryStore:
    """SQLite-backed memory store with WAL mode."""

    def __init__(self, db_path: str = "data/chatpilot.db") -> None:
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def initialize(self) -> None:
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self._db_path)
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.executescript(CREATE_TABLES)
        await self._db.commit()
        logger.info("MemoryStore initialized at %s", self._db_path)

    async def close(self) -> None:
        if self._db:
            await self._db.close()

    def _validate_type(self, type: str) -> tuple[type, str, str | None]:
        if type not in TYPE_REGISTRY:
            raise ValueError(f"Unknown memory type: {type}")
        return TYPE_REGISTRY[type]

    async def save(self, route_id: str, type: str, data: dict) -> str:
        model_cls, table, _ = self._validate_type(type)
        if self._db is None:
            raise RuntimeError("MemoryStore not initialized")

        if "id" not in data:
            data["id"] = str(uuid.uuid4())
        data["route_id"] = route_id
        if "created_at" not in data:
            data["created_at"] = datetime.now(timezone.utc).isoformat()

        obj = model_cls.model_validate(data)
        row = obj.model_dump(mode="json")
        _serialize_json_fields(row)

        cols = ", ".join(row.keys())
        placeholders = ", ".join(["?"] * len(row))
        await self._db.execute(
            f"INSERT INTO {table} ({cols}) VALUES ({placeholders})",
            list(row.values()),
        )
        await self._db.commit()
        logger.info("Saved %s/%s id=%s", type, route_id[:16], obj.id[:8])
        return obj.id

    async def get(
        self, route_id: str, type: str, id: str
    ) -> dict | None:
        _, table, _ = self._validate_type(type)
        if self._db is None:
            raise RuntimeError("MemoryStore not initialized")

        async with self._db.execute(
            f"SELECT * FROM {table} WHERE id = ? AND route_id = ?",
            (id, route_id),
        ) as cursor:
            row = await cursor.fetchone()
            if row is None:
                return None
            cols = [d[0] for d in cursor.description]
            return _deserialize_row(dict(zip(cols, row)))

    async def list(self, route_id: str, type: str) -> list[dict]:
        _, table, _ = self._validate_type(type)
        if self._db is None:
            raise RuntimeError("MemoryStore not initialized")

        async with self._db.execute(
            f"SELECT * FROM {table} WHERE route_id = ? "
            f"ORDER BY created_at DESC",
            (route_id,),
        ) as cursor:
            rows = await cursor.fetchall()
            cols = [d[0] for d in cursor.description]
            return [
                _deserialize_row(dict(zip(cols, r))) for r in rows
            ]

    async def delete(
        self, route_id: str, type: str, id: str
    ) -> bool:
        _, table, _ = self._validate_type(type)
        if self._db is None:
            raise RuntimeError("MemoryStore not initialized")

        cursor = await self._db.execute(
            f"DELETE FROM {table} WHERE id = ? AND route_id = ?",
            (id, route_id),
        )
        await self._db.commit()
        deleted = cursor.rowcount > 0
        if deleted:
            logger.info("Deleted %s/%s id=%s", type, route_id[:16], id[:8])
        return deleted

    async def update(
        self, route_id: str, type: str, id: str, data: dict
    ) -> None:
        _, table, _ = self._validate_type(type)
        if self._db is None:
            raise RuntimeError("MemoryStore not initialized")

        _serialize_json_fields(data)
        sets = ", ".join(f"{k} = ?" for k in data)
        values = list(data.values()) + [id, route_id]
        await self._db.execute(
            f"UPDATE {table} SET {sets} WHERE id = ? AND route_id = ?",
            values,
        )
        await self._db.commit()

    async def query_due_before(
        self, type: str, before: datetime
    ) -> list[dict]:
        """Query pending items due before given time (cross-route)."""
        _, table, time_field = self._validate_type(type)
        if time_field is None:
            return []
        if self._db is None:
            raise RuntimeError("MemoryStore not initialized")

        before_str = before.isoformat()
        async with self._db.execute(
            f"SELECT * FROM {table} "
            f"WHERE status = ? AND {time_field} <= ?",
            (MemoryStatus.pending.value, before_str),
        ) as cursor:
            rows = await cursor.fetchall()
            cols = [d[0] for d in cursor.description]
            return [
                _deserialize_row(dict(zip(cols, r))) for r in rows
            ]


def _serialize_json_fields(data: dict) -> None:
    """Convert list/dict fields to JSON strings for SQLite."""
    if "tags" in data and isinstance(data["tags"], list):
        data["tags"] = json.dumps(data["tags"], ensure_ascii=False)
    if "input_data" in data and isinstance(data["input_data"], dict):
        data["input_data"] = json.dumps(
            data["input_data"], ensure_ascii=False
        )


def _deserialize_row(row: dict) -> dict:
    """Parse JSON string fields back to Python objects."""
    if "tags" in row and isinstance(row["tags"], str):
        try:
            row["tags"] = json.loads(row["tags"])
        except (json.JSONDecodeError, TypeError):
            row["tags"] = []
    if "input_data" in row and isinstance(row["input_data"], str):
        try:
            row["input_data"] = json.loads(row["input_data"])
        except (json.JSONDecodeError, TypeError):
            row["input_data"] = {}
    return row
