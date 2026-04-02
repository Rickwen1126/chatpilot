"""Route key migration helpers for named LINE channels."""

from __future__ import annotations

import argparse
import json
import sqlite3
import uuid
from dataclasses import dataclass
from pathlib import Path

LINE_ROUTE_TABLES: tuple[tuple[str, str], ...] = (
    ("memory_memos", "route_id"),
    ("memory_custom_prompts", "route_id"),
    ("memory_reminders", "route_id"),
    ("memory_schedules", "route_id"),
    ("memory_observations", "route_id"),
    ("trigger_keywords", "route_id"),
)

TASK_ROUTE_TABLES: tuple[tuple[str, str], ...] = (("tasks", "chat_route_id"),)


@dataclass(slots=True)
class MigrationSummary:
    labels_copied: int = 0
    memory_rows_copied: int = 0
    task_rows_copied: int = 0


def to_named_line_route(route_id: str, channel: str) -> str | None:
    """Map a legacy LINE route key to named-channel form."""
    named_prefix = f"line:{channel}:"
    if route_id.startswith(named_prefix):
        return None
    if not route_id.startswith("line:"):
        return None

    tail = route_id[len("line:") :]
    if ":" in tail:
        return None

    malformed_suffix = f"-{channel}"
    if tail.endswith(malformed_suffix):
        tail = tail[: -len(malformed_suffix)]

    if not tail or tail[0] not in {"C", "U", "R"}:
        return None

    return f"{named_prefix}{tail}"


def migrate_route_labels(
    labels_path: Path, channel: str
) -> int:
    """Copy legacy LINE labels to named-channel keys."""
    if not labels_path.exists():
        return 0

    labels = json.loads(labels_path.read_text(encoding="utf-8"))
    copied = 0
    for route_id, label in list(labels.items()):
        new_route_id = to_named_line_route(route_id, channel)
        if new_route_id is None or new_route_id in labels:
            continue
        labels[new_route_id] = label
        copied += 1

    if copied:
        labels_path.write_text(
            json.dumps(labels, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    return copied


def _table_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return [row[1] for row in rows]


def _copy_route_rows(
    conn: sqlite3.Connection,
    table: str,
    route_column: str,
    channel: str,
) -> int:
    columns = _table_columns(conn, table)
    if not columns:
        return 0
    rows = conn.execute(
        f"SELECT {', '.join(columns)} FROM {table} WHERE {route_column} LIKE 'line:%'"
    ).fetchall()
    copied = 0

    for row in rows:
        row_data = dict(zip(columns, row))
        route_id = row_data[route_column]
        new_route_id = to_named_line_route(route_id, channel)
        if new_route_id is None:
            continue

        natural_columns = [
            column for column in columns if column not in {"id", route_column}
        ]
        where_clause = " AND ".join(
            [f"{route_column} = ?"] + [f"{column} IS ?" for column in natural_columns]
        )
        where_values = [new_route_id] + [row_data[column] for column in natural_columns]
        exists = conn.execute(
            f"SELECT 1 FROM {table} WHERE {where_clause} LIMIT 1", where_values
        ).fetchone()
        if exists:
            continue

        insert_data = dict(row_data)
        insert_data[route_column] = new_route_id
        if "id" in insert_data:
            insert_data["id"] = str(uuid.uuid4())

        insert_columns = list(insert_data.keys())
        placeholders = ", ".join(["?"] * len(insert_columns))
        conn.execute(
            f"INSERT INTO {table} ({', '.join(insert_columns)}) VALUES ({placeholders})",
            [insert_data[column] for column in insert_columns],
        )
        copied += 1

    return copied


def migrate_sqlite_routes(
    db_path: Path,
    channel: str,
    tables: tuple[tuple[str, str], ...],
) -> int:
    """Copy legacy LINE route-scoped rows to named-channel keys."""
    if not db_path.exists():
        return 0

    copied = 0
    conn = sqlite3.connect(db_path)
    try:
        for table, route_column in tables:
            copied += _copy_route_rows(conn, table, route_column, channel)
        conn.commit()
    finally:
        conn.close()
    return copied


def migrate_named_line_routes(
    data_dir: Path,
    channel: str,
) -> MigrationSummary:
    """Copy local legacy LINE route data to named-channel keys."""
    summary = MigrationSummary()
    summary.labels_copied = migrate_route_labels(data_dir / "route_labels.json", channel)
    summary.memory_rows_copied = migrate_sqlite_routes(
        data_dir / "chatpilot.db", channel, LINE_ROUTE_TABLES
    )
    summary.task_rows_copied = migrate_sqlite_routes(
        data_dir / "tasks.db", channel, TASK_ROUTE_TABLES
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate legacy LINE route keys")
    parser.add_argument(
        "--channel",
        required=True,
        help="Named LINE channel, for example shinyipaint",
    )
    parser.add_argument(
        "--data-dir",
        default="data",
        help="Data directory containing chatpilot.db/tasks.db/route_labels.json",
    )
    args = parser.parse_args()

    summary = migrate_named_line_routes(Path(args.data_dir), args.channel)
    print(
        json.dumps(
            {
                "channel": args.channel,
                "data_dir": str(Path(args.data_dir)),
                "labels_copied": summary.labels_copied,
                "memory_rows_copied": summary.memory_rows_copied,
                "task_rows_copied": summary.task_rows_copied,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
