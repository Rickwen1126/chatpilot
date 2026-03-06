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

from chatpilot.core.types import RouteConfig

logger = logging.getLogger(__name__)


def load_route_config(path: str) -> RouteConfig:
    """Load and validate routes from YAML using RouteConfig schema."""
    raw = Path(path).read_text(encoding="utf-8")
    data = yaml.safe_load(raw)
    if data is None:
        return RouteConfig(agent_list=[], platforms={})
    return RouteConfig.model_validate(data)


def save_route_config(path: str, config: RouteConfig) -> None:
    """Write RouteConfig back to YAML file."""
    data = config.model_dump(by_alias=True, exclude_none=True)
    output = yaml.dump(
        data, default_flow_style=False, allow_unicode=True, sort_keys=False
    )
    Path(path).write_text(output, encoding="utf-8")
    logger.info("RouteConfig saved to %s", path)


class RouteWatcher:
    """Watches routes.yaml for changes and reloads on modification."""

    def __init__(
        self,
        path: str,
        on_change: Callable[[RouteConfig], None],
    ) -> None:
        self._path = path
        self._on_change = on_change
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
            new_config = load_route_config(self._path)
            self._on_change(new_config)
            logger.info(
                "RouteConfig reloaded: %d platform(s) from %s",
                len(new_config.platforms),
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
