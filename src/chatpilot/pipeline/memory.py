"""Memory Tool — per-task JSON file-based KV store for cross-node context."""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class MemoryStore:
    """Per-task key-value memory store backed by JSON files.

    Storage layout: data/memory/{task_id}/memory.json
    """

    def __init__(self, data_dir: str = "data/memory") -> None:
        self._data_dir = Path(data_dir)

    def _get_path(self, task_id: str) -> Path:
        return self._data_dir / task_id / "memory.json"

    def _load(self, task_id: str) -> dict:
        path = self._get_path(task_id)
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def _save(self, task_id: str, data: dict) -> None:
        path = self._get_path(task_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    async def get(self, task_id: str, key: str) -> object:
        data = self._load(task_id)
        return data.get(key)

    async def set(self, task_id: str, key: str, value: object) -> None:
        data = self._load(task_id)
        data[key] = value
        self._save(task_id, data)

    async def list_keys(self, task_id: str) -> list[str]:
        data = self._load(task_id)
        return list(data.keys())

    async def delete(self, task_id: str, key: str) -> None:
        data = self._load(task_id)
        data.pop(key, None)
        self._save(task_id, data)
