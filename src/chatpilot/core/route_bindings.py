"""Machine-managed route bindings store and runtime service."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

from chatpilot.core.types import Binding, ObservationConfig, RouteOnboardingState


class RouteBindingEntry(Binding):
    """Exact route binding persisted by humans or discovery/admin flows."""

    source: Literal["manual", "discovered"] = "manual"
    profile_name: str | None = None
    discovered_at: datetime | None = None

    def as_binding(self) -> Binding:
        return Binding.model_validate(
            self.model_dump(
                include={
                    "match",
                    "chatbot",
                    "reply_policy",
                    "processing_policy",
                    "observation",
                }
            )
        )


class RouteBindingsConfig(BaseModel):
    """Single source of truth for all route bindings."""

    route_bindings: dict[str, RouteBindingEntry] = Field(default_factory=dict)
    fallback_bindings: list[Binding] = Field(default_factory=list)

    def merged_bindings(self) -> list[Binding]:
        return (
            [entry.as_binding() for entry in self.route_bindings.values()]
            + list(self.fallback_bindings)
        )


RouteBindingEntry.model_rebuild(_types_namespace={"ObservationConfig": ObservationConfig})
RouteBindingsConfig.model_rebuild(
    _types_namespace={"RouteBindingEntry": RouteBindingEntry}
)


def load_route_bindings(path: Path) -> RouteBindingsConfig:
    if not path.exists():
        return RouteBindingsConfig()
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if raw is None:
        raw = {}
    return RouteBindingsConfig.model_validate(raw)


class RouteBindingService:
    """Write-through service for persisted exact route bindings."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._config = RouteBindingsConfig()

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> None:
        self._config = load_route_bindings(self._path)

    def config(self) -> RouteBindingsConfig:
        return self._config

    def merged_bindings(self) -> list[Binding]:
        return self._config.merged_bindings()

    def get_entry(self, route_id: str) -> RouteBindingEntry | None:
        return self._config.route_bindings.get(route_id)

    def list_entries(self) -> list[tuple[str, RouteBindingEntry]]:
        return list(self._config.route_bindings.items())

    def replace_fallback_bindings(self, bindings: list[Binding]) -> None:
        self._config.fallback_bindings = list(bindings)

    def upsert_entry(self, route_id: str, entry: RouteBindingEntry) -> RouteBindingEntry:
        existing = self._config.route_bindings.get(route_id)
        if existing is not None and existing.source == "manual" and entry.source != "manual":
            return existing
        self._config.route_bindings[route_id] = entry
        return entry

    def upsert_from_onboarding(
        self, state: RouteOnboardingState
    ) -> RouteBindingEntry:
        match = {"platform": state.platform}
        if state.route_type == "group":
            match["group_id"] = state.conversation_id
        else:
            match["user_id"] = state.conversation_id
        entry = RouteBindingEntry(
            match=match,
            chatbot=state.chatbot,
            reply_policy=state.reply_policy,
            processing_policy=state.processing_policy,
            observation=state.observation,
            source="discovered",
            profile_name=state.profile_name,
            discovered_at=state.discovered_at,
        )
        return self.upsert_entry(state.route_id, entry)

    def save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = self._config.model_dump(mode="json")
        self._path.write_text(
            yaml.safe_dump(
                json.loads(json.dumps(payload)),
                allow_unicode=True,
                sort_keys=False,
            ),
            encoding="utf-8",
        )
