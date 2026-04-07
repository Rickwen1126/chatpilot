"""SqliteMemoryStore — SQLite-backed memory store implementation."""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime
from pathlib import Path

import aiosqlite

from chatpilot.memory.types import (
    CustomPrompt,
    Memo,
    MemoryStatus,
    Observation,
    ObservationEntry,
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
    "observation": (Observation, "memory_observations", None),
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
    tool_name      TEXT NOT NULL,
    chatbot_name   TEXT DEFAULT '',
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

CREATE TABLE IF NOT EXISTS memory_observations (
    id             TEXT PRIMARY KEY,
    route_id       TEXT NOT NULL,
    batch_time     TEXT NOT NULL,
    message_count  INTEGER DEFAULT 0,
    entries        TEXT DEFAULT '[]',
    summary        TEXT DEFAULT '',
    created_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_observations_route
    ON memory_observations(route_id);
CREATE INDEX IF NOT EXISTS idx_observations_time
    ON memory_observations(route_id, batch_time);

CREATE TABLE IF NOT EXISTS observation_entries (
    id                   TEXT PRIMARY KEY,
    route_id             TEXT NOT NULL,
    captured_profile_name TEXT NOT NULL DEFAULT '',
    kind                 TEXT NOT NULL DEFAULT 'fact',
    canonical_entry_id   TEXT,
    category             TEXT NOT NULL DEFAULT '其他',
    subject              TEXT NOT NULL DEFAULT '',
    record_date          TEXT NOT NULL DEFAULT '',
    content              TEXT NOT NULL DEFAULT '',
    search_text          TEXT NOT NULL DEFAULT '',
    reported_by_user_id  TEXT,
    reported_by_name     TEXT,
    facets_json          TEXT NOT NULL DEFAULT '{}',
    source_observation_id TEXT NOT NULL,
    created_at           TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_observation_entries_route
    ON observation_entries(route_id);
CREATE INDEX IF NOT EXISTS idx_observation_entries_route_date
    ON observation_entries(route_id, record_date);
CREATE INDEX IF NOT EXISTS idx_observation_entries_source
    ON observation_entries(source_observation_id);
CREATE INDEX IF NOT EXISTS idx_observation_entries_kind
    ON observation_entries(kind);

CREATE TABLE IF NOT EXISTS trigger_keywords (
    id          TEXT PRIMARY KEY,
    route_id    TEXT NOT NULL,
    keyword     TEXT NOT NULL,
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_trigger_keywords_route
    ON trigger_keywords(route_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_trigger_keywords_unique
    ON trigger_keywords(route_id, keyword);
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
        await self._migrate()
        await self._db.commit()
        logger.info("MemoryStore initialized at %s", self._db_path)

    async def _migrate(self) -> None:
        """Run schema migrations for existing databases."""
        if self._db is None:
            return
        # Rename pipeline_name → tool_name in memory_schedules
        async with self._db.execute(
            "PRAGMA table_info(memory_schedules)"
        ) as cursor:
            cols = [row[1] for row in await cursor.fetchall()]
        if "pipeline_name" in cols and "tool_name" not in cols:
            await self._db.execute(
                "ALTER TABLE memory_schedules "
                "RENAME COLUMN pipeline_name TO tool_name"
            )
            logger.info("Migrated memory_schedules: pipeline_name → tool_name")
        if "chatbot_name" not in cols:
            await self._db.execute(
                "ALTER TABLE memory_schedules "
                "ADD COLUMN chatbot_name TEXT DEFAULT ''"
            )
            logger.info("Migrated memory_schedules: added chatbot_name")

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
            from chatpilot.core.time_service import TimeService

            data["created_at"] = TimeService.get().utc_now().isoformat()

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
        logger.info(
            "[db] SAVE %s route=%s id=%s data=%s",
            type, route_id[:16], obj.id[:8], row,
        )
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
            logger.info("[db] DELETE %s route=%s id=%s", type, route_id[:16], id[:8])
        else:
            logger.info("[db] DELETE miss %s route=%s id=%s", type, route_id[:16], id[:8])
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

    async def query_observations(
        self,
        route_id: str,
        days: int = 7,
        category: str = "",
    ) -> list[dict]:
        """Query observations for a route, optionally filtered by category."""
        if self._db is None:
            raise RuntimeError("MemoryStore not initialized")
        from datetime import timedelta

        from chatpilot.core.time_service import TimeService

        since = (
            TimeService.get().utc_now() - timedelta(days=days)
        ).isoformat()
        async with self._db.execute(
            "SELECT * FROM memory_observations "
            "WHERE route_id = ? AND batch_time >= ? "
            "ORDER BY batch_time DESC",
            (route_id, since),
        ) as cursor:
            rows = await cursor.fetchall()
            cols = [d[0] for d in cursor.description]
            results = [
                _deserialize_row(dict(zip(cols, r))) for r in rows
            ]

        if category:
            for obs in results:
                obs["entries"] = [
                    e for e in obs.get("entries", [])
                    if e.get("category", "") == category
                ]
            results = [r for r in results if r["entries"]]

        return results

    async def save_observation_entries(
        self, entries: list[ObservationEntry]
    ) -> list[str]:
        """Persist route-owned retrieval projection rows."""
        if self._db is None:
            raise RuntimeError("MemoryStore not initialized")
        if not entries:
            return []

        rows: list[dict] = []
        for entry in entries:
            row = entry.model_dump(mode="json")
            _serialize_json_fields(row)
            rows.append(row)

        cols = ", ".join(rows[0].keys())
        placeholders = ", ".join(["?"] * len(rows[0]))
        values = [tuple(row.values()) for row in rows]
        await self._db.executemany(
            f"INSERT INTO observation_entries ({cols}) VALUES ({placeholders})",
            values,
        )
        await self._db.commit()
        logger.info(
            "[db] SAVE observation_entries route=%s count=%d source=%s",
            entries[0].route_id[:16],
            len(entries),
            entries[0].source_observation_id[:8],
        )
        return [entry.id for entry in entries]

    async def list_observation_entries(self, route_id: str) -> list[dict]:
        if self._db is None:
            raise RuntimeError("MemoryStore not initialized")

        async with self._db.execute(
            "SELECT * FROM observation_entries "
            "WHERE route_id = ? ORDER BY created_at DESC",
            (route_id,),
        ) as cursor:
            rows = await cursor.fetchall()
            cols = [d[0] for d in cursor.description]
            return [_deserialize_row(dict(zip(cols, r))) for r in rows]

    async def get_observation_entries_by_ids(
        self, route_id: str, ids: list[str]
    ) -> list[dict]:
        """Fetch specific projected observation entries for one source route."""
        if self._db is None:
            raise RuntimeError("MemoryStore not initialized")
        if not ids:
            return []

        placeholders = ", ".join(["?"] * len(ids))
        sql = (
            "SELECT * FROM observation_entries "
            f"WHERE route_id = ? AND id IN ({placeholders})"
        )
        params: list[str] = [route_id, *ids]
        async with self._db.execute(sql, tuple(params)) as cursor:
            rows = await cursor.fetchall()
            cols = [d[0] for d in cursor.description]
            return [_deserialize_row(dict(zip(cols, r))) for r in rows]

    async def query_observation_entries(
        self,
        route_id: str,
        query: str = "",
        *,
        days: int = 30,
        limit: int = 20,
        kinds: tuple[str, ...] = ("fact", "semantic"),
    ) -> list[dict]:
        """Query projected observation entries for a single source route."""
        if self._db is None:
            raise RuntimeError("MemoryStore not initialized")

        from datetime import timedelta

        from chatpilot.core.time_service import TimeService

        since = (
            TimeService.get().utc_now() - timedelta(days=days)
        ).date().isoformat()
        placeholders = ", ".join(["?"] * len(kinds))
        sql = (
            "SELECT * FROM observation_entries "
            f"WHERE route_id = ? AND kind IN ({placeholders}) "
            "AND (record_date = '' OR record_date >= ?)"
            " ORDER BY record_date DESC, created_at DESC"
        )
        params: list[str | int] = [route_id, *kinds, since]

        async with self._db.execute(sql, tuple(params)) as cursor:
            rows = await cursor.fetchall()
            cols = [d[0] for d in cursor.description]
            hydrated = [_deserialize_row(dict(zip(cols, r))) for r in rows]

        if not query.strip():
            return hydrated[:limit]

        scored: list[tuple[int, dict]] = []
        for row in hydrated:
            score = _score_observation_entry(query, row)
            if score <= 0:
                continue
            scored.append((score, row))

        scored.sort(
            key=lambda item: (
                item[0],
                str(item[1].get("record_date", "")),
                str(item[1].get("created_at", "")),
            ),
            reverse=True,
        )
        return [row for _, row in scored[:limit]]

    # ── Trigger Keywords ─────────────────────────────────────────

    async def load_all_trigger_keywords(self) -> dict[str, list[str]]:
        """Load all trigger keywords grouped by route_id.

        Returns: {route_id: [keyword1, keyword2, ...]}
        Called once at startup to populate in-memory cache.
        """
        if self._db is None:
            raise RuntimeError("MemoryStore not initialized")
        result: dict[str, list[str]] = {}
        async with self._db.execute(
            "SELECT route_id, keyword FROM trigger_keywords ORDER BY created_at"
        ) as cursor:
            async for row in cursor:
                route_id, keyword = row
                result.setdefault(route_id, []).append(keyword)
        return result

    async def add_trigger_keyword(
        self, route_id: str, keyword: str
    ) -> str:
        """Add a trigger keyword for a route. Returns the keyword id."""
        if self._db is None:
            raise RuntimeError("MemoryStore not initialized")
        from chatpilot.core.time_service import TimeService

        kid = uuid.uuid4().hex
        await self._db.execute(
            "INSERT OR IGNORE INTO trigger_keywords "
            "(id, route_id, keyword, created_at) VALUES (?, ?, ?, ?)",
            (kid, route_id, keyword, TimeService.get().utc_now().isoformat()),
        )
        await self._db.commit()
        return kid

    async def remove_trigger_keyword(
        self, route_id: str, keyword: str
    ) -> bool:
        """Remove a trigger keyword for a route. Returns True if deleted."""
        if self._db is None:
            raise RuntimeError("MemoryStore not initialized")
        cursor = await self._db.execute(
            "DELETE FROM trigger_keywords WHERE route_id = ? AND keyword = ?",
            (route_id, keyword),
        )
        await self._db.commit()
        return cursor.rowcount > 0

    async def list_trigger_keywords(self, route_id: str) -> list[str]:
        """List all trigger keywords for a route."""
        if self._db is None:
            raise RuntimeError("MemoryStore not initialized")
        async with self._db.execute(
            "SELECT keyword FROM trigger_keywords "
            "WHERE route_id = ? ORDER BY created_at",
            (route_id,),
        ) as cursor:
            return [row[0] async for row in cursor]


def _serialize_json_fields(data: dict) -> None:
    """Convert list/dict fields to JSON strings for SQLite."""
    if "tags" in data and isinstance(data["tags"], list):
        data["tags"] = json.dumps(data["tags"], ensure_ascii=False)
    if "input_data" in data and isinstance(data["input_data"], dict):
        data["input_data"] = json.dumps(
            data["input_data"], ensure_ascii=False
        )
    if "entries" in data and isinstance(data["entries"], list):
        data["entries"] = json.dumps(
            data["entries"], ensure_ascii=False
        )
    if "facets_json" in data and isinstance(data["facets_json"], dict):
        data["facets_json"] = json.dumps(
            data["facets_json"], ensure_ascii=False
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
    if "entries" in row and isinstance(row["entries"], str):
        try:
            row["entries"] = json.loads(row["entries"])
        except (json.JSONDecodeError, TypeError):
            row["entries"] = []
    if "facets_json" in row and isinstance(row["facets_json"], str):
        try:
            row["facets_json"] = json.loads(row["facets_json"])
        except (json.JSONDecodeError, TypeError):
            row["facets_json"] = {}
    return row


def _score_observation_entry(query: str, row: dict) -> int:
    normalized_query = query.casefold().strip()
    terms = _extract_query_terms(query)
    if not terms:
        return 1

    category = str(row.get("category", "")).casefold()
    subject = str(row.get("subject", "")).casefold()
    content = str(row.get("content", "")).casefold()
    search_text = str(row.get("search_text", "")).casefold()
    reporter = str(row.get("reported_by_name", "")).casefold()
    score = 0

    if category and category in normalized_query:
        score += 6
    if subject and subject in normalized_query:
        score += 5

    for term in terms:
        if term and category and term in category:
            score += 5
        if term and subject and term in subject:
            score += 4
        if term and search_text and term in search_text:
            score += 3
        if term and content and term in content:
            score += 2
        if term and reporter and term in reporter:
            score += 1

    return score


def _extract_query_terms(query: str) -> list[str]:
    raw_terms = [term.strip().casefold() for term in query.split() if term.strip()]
    terms: list[str] = []
    seen: set[str] = set()
    for term in raw_terms or [query.casefold().strip()]:
        for candidate in _expand_term(term):
            if candidate in seen:
                continue
            seen.add(candidate)
            terms.append(candidate)
    return terms


def _expand_term(term: str) -> list[str]:
    candidates: list[str] = []
    text = term.strip().casefold()
    if not text:
        return candidates
    candidates.append(text)
    for part in re.findall(r"[a-z0-9_]{2,}|[\u4e00-\u9fff]{2,}", text):
        if part not in candidates:
            candidates.append(part)
        if _contains_cjk(part) and len(part) >= 4:
            for size in (2, 3):
                if len(part) < size:
                    continue
                for index in range(0, len(part) - size + 1):
                    piece = part[index : index + size]
                    if piece not in candidates:
                        candidates.append(piece)
    return candidates


def _contains_cjk(text: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in text)
