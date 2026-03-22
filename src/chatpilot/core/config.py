"""Config loader — parses routes.yaml into GatewayConfig."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

import yaml
from pydantic import BaseModel
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from chatpilot.core.types import (
    AgentConfig,
    Binding,
    ChatbotConfig,
    MatchWeights,
    SchedulerConfig,
)

logger = logging.getLogger(__name__)


class GatewayConfig(BaseModel):
    match_weights: MatchWeights = MatchWeights()
    bindings: list[Binding] = []
    chatbots: dict[str, ChatbotConfig] = {}
    agents: dict[str, AgentConfig] = {}
    scheduler: SchedulerConfig = SchedulerConfig()


def load_config(path: Path) -> GatewayConfig:
    """Load and validate gateway config from YAML file."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if raw is None:
        raw = {}
    # Inject chatbot name from dict key
    chatbots = {}
    for name, cfg in raw.get("chatbots", {}).items():
        if isinstance(cfg, dict):
            cfg["name"] = name
            chatbots[name] = cfg
    raw["chatbots"] = chatbots
    # Inject agent name from dict key
    agents = {}
    for name, cfg in raw.get("agents", {}).items():
        if isinstance(cfg, dict):
            cfg["name"] = name
            agents[name] = cfg
    raw["agents"] = agents
    return GatewayConfig.model_validate(raw)


class _ConfigReloadHandler(FileSystemEventHandler):
    def __init__(self, path: Path, callback: Callable[[GatewayConfig], None]):
        self._path = path
        self._callback = callback

    def on_modified(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        if Path(event.src_path).resolve() != self._path.resolve():
            return
        try:
            config = load_config(self._path)
            self._callback(config)
            logger.info("Config reloaded from %s", self._path)
        except Exception:
            logger.exception("Failed to reload config from %s", self._path)


def watch_config(path: Path, callback: Callable[[GatewayConfig], None]) -> Observer:
    """Start watching config file for changes. Returns the Observer (call .stop() to stop)."""
    handler = _ConfigReloadHandler(path.resolve(), callback)
    observer = Observer()
    observer.schedule(handler, str(path.resolve().parent), recursive=False)
    observer.daemon = True
    observer.start()
    logger.info("Watching config file: %s", path)
    return observer
