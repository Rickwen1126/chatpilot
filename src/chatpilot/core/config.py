"""Config loader — parses routes.yaml into GatewayConfig."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

import yaml
from pydantic import BaseModel, Field
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from chatpilot.core.types import (
    AdapterChannelConfig,
    AgentConfig,
    Binding,
    ChatbotConfig,
    CronSchedulerConfig,
    MatchWeights,
    SchedulerConfig,
)

logger = logging.getLogger(__name__)


class GatewayConfig(BaseModel):
    timezone: str = "Asia/Taipei"
    match_weights: MatchWeights = Field(default_factory=MatchWeights)
    bindings: list[Binding] = Field(default_factory=list)
    chatbots: dict[str, ChatbotConfig] = Field(default_factory=dict)
    agents: dict[str, AgentConfig] = Field(default_factory=dict)
    adapters: dict[str, list[AdapterChannelConfig]] = Field(default_factory=dict)
    scheduler: SchedulerConfig = Field(default_factory=SchedulerConfig)
    cron_scheduler: CronSchedulerConfig = Field(default_factory=CronSchedulerConfig)
    trigger_keywords: list[str] = Field(default_factory=list)


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
