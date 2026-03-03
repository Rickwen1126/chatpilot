"""Route loader — YAML parsing + watchdog hot-reload."""

from __future__ import annotations

import logging
import sys
import threading
from pathlib import Path
from typing import Callable

import yaml
from watchdog.events import FileModifiedEvent, FileSystemEventHandler
from watchdog.observers import Observer

from chatpilot.core.types import RouteMap

logger = logging.getLogger(__name__)


def load_routes(path: str) -> RouteMap:
    """Load and validate routes from a YAML file."""
    raw = Path(path).read_text(encoding="utf-8")
    data = yaml.safe_load(raw)
    if data is None:
        return RouteMap(routes=[])
    return RouteMap.model_validate(data)


class RouteWatcher:
    """Watches routes.yaml for changes and reloads on modification."""

    def __init__(
        self,
        path: str,
        on_change: Callable[[RouteMap], None],
        agent_registry: dict | None = None,
    ) -> None:
        self._path = path
        self._on_change = on_change
        self._agent_registry = agent_registry
        self._observer: Observer | None = None
        self._debounce_timer: threading.Timer | None = None

    def start(self) -> None:
        handler = _RouteFileHandler(self._path, self._reload)
        self._observer = Observer()
        self._observer.schedule(handler, str(Path(self._path).parent), recursive=False)
        self._observer.daemon = True
        self._observer.start()
        logger.info("RouteWatcher started for %s", self._path)

    def stop(self) -> None:
        if self._debounce_timer is not None:
            self._debounce_timer.cancel()
        if self._observer is not None:
            self._observer.stop()
            self._observer.join(timeout=5)
            self._observer = None
        logger.info("RouteWatcher stopped")

    def _reload(self) -> None:
        try:
            new_map = load_routes(self._path)
            if self._agent_registry is not None:
                _validate_agents(new_map, self._agent_registry)
            self._on_change(new_map)
            logger.info(
                "Route map reloaded: %d route(s) from %s",
                len(new_map.routes),
                self._path,
            )
        except Exception as e:
            print(f"[ROUTE ERROR] {e}", file=sys.stderr)
            logger.error("Route reload failed, keeping previous config: %s", e)

    def _debounced_reload(self) -> None:
        if self._debounce_timer is not None:
            self._debounce_timer.cancel()
        self._debounce_timer = threading.Timer(0.2, self._reload)
        self._debounce_timer.start()


class _RouteFileHandler(FileSystemEventHandler):
    def __init__(self, watch_path: str, reload_fn: Callable[[], None]) -> None:
        self._watch_path = str(Path(watch_path).resolve())
        self._reload_fn = reload_fn
        self._debounce_timer: threading.Timer | None = None

    def on_modified(self, event: FileModifiedEvent) -> None:
        if (
            hasattr(event, "src_path")
            and str(Path(event.src_path).resolve()) == self._watch_path
        ):
            if self._debounce_timer is not None:
                self._debounce_timer.cancel()
            self._debounce_timer = threading.Timer(0.2, self._reload_fn)
            self._debounce_timer.start()


def _validate_agents(route_map: RouteMap, agent_registry: dict) -> None:
    """Validate all agent names in the route map exist in the registry."""
    for rule in route_map.routes:
        for kw in rule.keywords:
            if kw.agent_name not in agent_registry:
                raise ValueError(f"unknown agent: {kw.agent_name}")
        if rule.fallback_agent and rule.fallback_agent not in agent_registry:
            raise ValueError(f"unknown agent: {rule.fallback_agent}")
