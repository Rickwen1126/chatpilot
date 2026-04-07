"""Machine-managed route bindings store and runtime service."""

from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, model_validator

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

    route_bindings_manual: dict[str, RouteBindingEntry] = Field(default_factory=dict)
    route_bindings_auto: dict[str, RouteBindingEntry] = Field(default_factory=dict)
    fallback_bindings: list[Binding] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy_route_bindings(cls, data):
        if not isinstance(data, dict):
            return data
        if "route_bindings" not in data:
            return data
        if "route_bindings_manual" in data or "route_bindings_auto" in data:
            return data
        legacy = data.pop("route_bindings") or {}
        manual: dict[str, object] = {}
        auto: dict[str, object] = {}
        for route_id, entry in legacy.items():
            source = (entry or {}).get("source", "manual")
            if source == "discovered":
                auto[route_id] = entry
            else:
                manual[route_id] = entry
        data["route_bindings_manual"] = manual
        data["route_bindings_auto"] = auto
        return data

    def merged_bindings(self) -> list[Binding]:
        return (
            [entry.as_binding() for entry in self.route_bindings_auto.values()]
            + [entry.as_binding() for entry in self.route_bindings_manual.values()]
            + list(self.fallback_bindings)
        )

    def merged_entries(self) -> dict[str, RouteBindingEntry]:
        merged = dict(self.route_bindings_auto)
        merged.update(self.route_bindings_manual)
        return merged


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
        self._last_self_write: dict[str, object] | None = None

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
        return (
            self._config.route_bindings_manual.get(route_id)
            or self._config.route_bindings_auto.get(route_id)
        )

    def list_entries(self) -> list[tuple[str, RouteBindingEntry]]:
        return list(self._config.merged_entries().items())

    def replace_fallback_bindings(self, bindings: list[Binding]) -> None:
        self._config.fallback_bindings = list(bindings)

    def upsert_entry(self, route_id: str, entry: RouteBindingEntry) -> RouteBindingEntry:
        existing_manual = self._config.route_bindings_manual.get(route_id)
        if existing_manual is not None and entry.source != "manual":
            return existing_manual
        if entry.source == "manual":
            self._config.route_bindings_manual[route_id] = entry
            return entry
        self._config.route_bindings_auto[route_id] = entry
        return entry

    def upsert_manual_entry(
        self,
        route_id: str,
        entry: RouteBindingEntry,
    ) -> RouteBindingEntry:
        if entry.source != "manual":
            entry = entry.model_copy(update={"source": "manual"})
        self._config.route_bindings_manual[route_id] = entry
        return entry

    def remove_auto_entry(self, route_id: str) -> None:
        self._config.route_bindings_auto.pop(route_id, None)

    def remove_manual_entry(self, route_id: str) -> None:
        self._config.route_bindings_manual.pop(route_id, None)

    def _mark_self_write(self, content: str) -> None:
        self._last_self_write = {
            "path": self._path.resolve(),
            "digest": hashlib.sha256(content.encode("utf-8")).hexdigest(),
            "at": time.monotonic(),
        }

    def should_skip_self_write(
        self,
        path: Path,
        window_seconds: float = 5.0,
    ) -> bool:
        token = self._last_self_write
        if token is None:
            return False
        if path.resolve() != token["path"]:
            return False
        if time.monotonic() - float(token["at"]) > window_seconds:
            return False
        if not path.exists():
            return False
        digest = hashlib.sha256(
            path.read_text(encoding="utf-8").encode("utf-8")
        ).hexdigest()
        return digest == token["digest"]

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
        content = yaml.safe_dump(
            json.loads(json.dumps(payload)),
            allow_unicode=True,
            sort_keys=False,
        )
        self._path.write_text(content, encoding="utf-8")
        self._mark_self_write(content)
