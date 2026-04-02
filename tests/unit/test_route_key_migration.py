from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from chatpilot.storage.route_key_migration import (
    migrate_named_line_routes,
    to_named_line_route,
)

CHATPILOT_SCHEMA = """
CREATE TABLE memory_custom_prompts (
    id TEXT PRIMARY KEY,
    route_id TEXT NOT NULL,
    text TEXT NOT NULL,
    category TEXT DEFAULT 'general',
    created_at TEXT NOT NULL
);
CREATE TABLE trigger_keywords (
    id TEXT PRIMARY KEY,
    route_id TEXT NOT NULL,
    keyword TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE UNIQUE INDEX idx_trigger_keywords_unique
    ON trigger_keywords(route_id, keyword);
"""

TASK_SCHEMA = """
CREATE TABLE tasks (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    duration_ms INTEGER,
    input_summary TEXT,
    output_summary TEXT,
    output_full TEXT,
    chat_route_id TEXT NOT NULL,
    pipeline_name TEXT NOT NULL,
    error TEXT,
    input_data TEXT DEFAULT '{}',
    reply_mode TEXT DEFAULT 'direct'
);
"""


def _executescript(path: Path, script: str) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.executescript(script)
        conn.commit()
    finally:
        conn.close()


def test_to_named_line_route_handles_legacy_named_and_malformed() -> None:
    assert (
        to_named_line_route("line:C123", "shinyipaint")
        == "line:shinyipaint:C123"
    )
    assert (
        to_named_line_route("line:U123-shinyipaint", "shinyipaint")
        == "line:shinyipaint:U123"
    )
    assert to_named_line_route("line:shinyipaint:C123", "shinyipaint") is None
    assert to_named_line_route("mock:C123", "shinyipaint") is None


def test_migrate_named_line_routes_copies_labels_memory_and_tasks(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    labels_path = data_dir / "route_labels.json"
    labels_path.write_text(
        json.dumps(
            {
                "line:C123": "Bot 測試群",
                "line:shinyipaint:U999": "Named private",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    chatpilot_db = data_dir / "chatpilot.db"
    _executescript(chatpilot_db, CHATPILOT_SCHEMA)
    conn = sqlite3.connect(chatpilot_db)
    try:
        conn.execute(
            "INSERT INTO memory_custom_prompts VALUES (?, ?, ?, ?, ?)",
            ("cp1", "line:C123", "legacy prompt", "general", "2026-04-03T00:00:00Z"),
        )
        conn.execute(
            "INSERT INTO trigger_keywords VALUES (?, ?, ?, ?)",
            ("kw1", "line:U123-shinyipaint", "bot", "2026-04-03T00:00:00Z"),
        )
        conn.commit()
    finally:
        conn.close()

    tasks_db = data_dir / "tasks.db"
    _executescript(tasks_db, TASK_SCHEMA)
    conn = sqlite3.connect(tasks_db)
    try:
        conn.execute(
            "INSERT INTO tasks VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "task1",
                "done",
                "2026-04-03T00:00:00Z",
                None,
                None,
                None,
                "summary",
                "output",
                "full",
                "line:C123",
                "observer",
                None,
                "{}",
                "direct",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    first = migrate_named_line_routes(data_dir, "shinyipaint")
    second = migrate_named_line_routes(data_dir, "shinyipaint")

    assert first.labels_copied == 1
    assert first.memory_rows_copied == 2
    assert first.task_rows_copied == 1
    assert second.labels_copied == 0
    assert second.memory_rows_copied == 0
    assert second.task_rows_copied == 0

    labels = json.loads(labels_path.read_text(encoding="utf-8"))
    assert labels["line:shinyipaint:C123"] == "Bot 測試群"

    conn = sqlite3.connect(chatpilot_db)
    try:
        prompt_count = conn.execute(
            "SELECT count(*) FROM memory_custom_prompts WHERE route_id = ?",
            ("line:shinyipaint:C123",),
        ).fetchone()[0]
        keyword_count = conn.execute(
            "SELECT count(*) FROM trigger_keywords WHERE route_id = ? AND keyword = ?",
            ("line:shinyipaint:U123", "bot"),
        ).fetchone()[0]
    finally:
        conn.close()

    conn = sqlite3.connect(tasks_db)
    try:
        task_count = conn.execute(
            "SELECT count(*) FROM tasks WHERE chat_route_id = ?",
            ("line:shinyipaint:C123",),
        ).fetchone()[0]
    finally:
        conn.close()

    assert prompt_count == 1
    assert keyword_count == 1
    assert task_count == 1
