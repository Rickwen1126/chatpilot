"""Config loader — parses route settings + route bindings into GatewayConfig."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

import yaml
from pydantic import BaseModel, Field, model_validator
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from chatpilot.core.route_bindings import load_route_bindings
from chatpilot.core.types import (
    AdapterChannelConfig,
    AgentConfig,
    Binding,
    ChatbotConfig,
    CronSchedulerConfig,
    DiscoveryProfileConfig,
    DiscoveryRuleConfig,
    MatchWeights,
    ObservationProfileConfig,
    RouteGroupConfig,
    SchedulerConfig,
)

logger = logging.getLogger(__name__)


class GatewayConfig(BaseModel):
    timezone: str = "Asia/Taipei"
    match_weights: MatchWeights = Field(default_factory=MatchWeights)
    route_groups: dict[str, RouteGroupConfig] = Field(default_factory=dict)
    observation_profiles: dict[str, ObservationProfileConfig] = Field(
        default_factory=dict
    )
    discovery_profiles: dict[str, DiscoveryProfileConfig] = Field(default_factory=dict)
    discovery_rules: list[DiscoveryRuleConfig] = Field(default_factory=list)
    bindings: list[Binding] = Field(default_factory=list)
    chatbots: dict[str, ChatbotConfig] = Field(default_factory=dict)
    agents: dict[str, AgentConfig] = Field(default_factory=dict)
    adapters: dict[str, list[AdapterChannelConfig]] = Field(default_factory=dict)
    scheduler: SchedulerConfig = Field(default_factory=SchedulerConfig)
    cron_scheduler: CronSchedulerConfig = Field(default_factory=CronSchedulerConfig)
    trigger_keywords: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_observer_vnext_refs(self) -> GatewayConfig:
        for profile_name, profile in self.discovery_profiles.items():
            if profile.chatbot not in self.chatbots:
                raise ValueError(
                    f"discovery_profile '{profile_name}' references unknown "
                    f"chatbot '{profile.chatbot}'"
                )
            obs = profile.observation
            if obs is None:
                continue
            if obs.capture is not None:
                if obs.capture.group not in self.route_groups:
                    raise ValueError(
                        "discovery_profile observation.capture.group references "
                        f"unknown route_group '{obs.capture.group}'"
                    )
                if obs.capture.profile not in self.observation_profiles:
                    raise ValueError(
                        "discovery_profile observation.capture.profile references "
                        f"unknown observation_profile '{obs.capture.profile}'"
                    )
            for group in obs.consume:
                if group not in self.route_groups:
                    raise ValueError(
                        "discovery_profile observation.consume references "
                        f"unknown route_group '{group}'"
                    )

        for rule in self.discovery_rules:
            if rule.profile not in self.discovery_profiles:
                raise ValueError(
                    f"discovery_rule references unknown profile '{rule.profile}'"
                )

        for binding in self.bindings:
            obs = binding.observation
            if obs is None:
                continue
            if obs.capture is not None:
                if obs.capture.group not in self.route_groups:
                    raise ValueError(
                        f"binding observation.capture.group references unknown "
                        f"route_group '{obs.capture.group}'"
                    )
                if obs.capture.profile not in self.observation_profiles:
                    raise ValueError(
                        "binding observation.capture.profile references "
                        f"unknown observation_profile '{obs.capture.profile}'"
                    )
            for group in obs.consume:
                if group not in self.route_groups:
                    raise ValueError(
                        f"binding observation.consume references unknown "
                        f"route_group '{group}'"
                    )
        return self


def load_config(path: Path, bindings_path: Path | None = None) -> GatewayConfig:
    """Load and validate gateway config from settings YAML plus route bindings."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if raw is None:
        raw = {}
    legacy_bindings = raw.pop("bindings", None)
    bindings_doc = (
        load_route_bindings(bindings_path)
        if bindings_path is not None
        else None
    )
    if bindings_doc is not None and (
        bindings_doc.route_bindings_manual
        or bindings_doc.route_bindings_auto
        or bindings_doc.fallback_bindings
    ):
        raw["bindings"] = bindings_doc.merged_bindings()
    elif legacy_bindings is not None:
        raw["bindings"] = legacy_bindings
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
    def __init__(
        self,
        paths: list[Path],
        loader: Callable[[], GatewayConfig],
        callback: Callable[[GatewayConfig], None],
        should_skip: Callable[[Path], bool] | None = None,
    ):
        self._paths = [path.resolve() for path in paths]
        self._loader = loader
        self._callback = callback
        self._should_skip = should_skip

    def on_modified(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        event_path = Path(event.src_path).resolve()
        if event_path not in self._paths:
            return
        if self._should_skip is not None and self._should_skip(event_path):
            logger.info("Skipping self-authored config write: %s", event_path)
            return
        try:
            config = self._loader()
            self._callback(config)
            logger.info("Config reloaded from %s", event_path)
        except Exception:
            logger.exception("Failed to reload config from %s", event_path)


def watch_config(
    paths: list[Path],
    loader: Callable[[], GatewayConfig],
    callback: Callable[[GatewayConfig], None],
    should_skip: Callable[[Path], bool] | None = None,
) -> Observer:
    """Start watching config files for changes. Returns the Observer (call .stop() to stop)."""
    resolved_paths = [path.resolve() for path in paths]
    handler = _ConfigReloadHandler(resolved_paths, loader, callback, should_skip)
    observer = Observer()
    seen_dirs: set[Path] = set()
    for path in resolved_paths:
        parent = path.parent
        if parent in seen_dirs:
            continue
        observer.schedule(handler, str(parent), recursive=False)
        seen_dirs.add(parent)
    observer.daemon = True
    observer.start()
    logger.info("Watching config files: %s", ", ".join(str(p) for p in resolved_paths))
    return observer
