"""Warehouse DB skill — loads full inventory from SQLite for LLM context."""

from __future__ import annotations

import os
import sqlite3

_DB_PATH = os.environ.get(
    "WAREHOUSE_DB",
    os.path.expanduser(
        "~/code/shinyipaint-proj-1/warehouse/"
        "warehouse-app/backend/warehouse.db"
    ),
)


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def load_full_inventory() -> str:
    """Load entire inventory as text for LLM context.

    ~304 items, ~5k tokens — small enough to fit in any model's context.
    """
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT unit_id, layer_key, name, quantity, unit_of_measure "
            "FROM items ORDER BY unit_id, layer_key, name"
        ).fetchall()
        if not rows:
            return "（倉庫目前沒有任何庫存資料）"
        lines = []
        for r in rows:
            lines.append(
                f"{r['unit_id']}/{r['layer_key']}: "
                f"{r['name']} ×{r['quantity']}{r['unit_of_measure']}"
            )
        return "\n".join(lines)
    finally:
        conn.close()
