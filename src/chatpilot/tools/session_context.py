"""Session context registry and helpers for tool/runtime identity."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from chatpilot.core.types import SessionContext

SESSION_CONTEXT_FILENAME = "session_context.json"
SESSION_CONTEXT_METADATA_DIR = Path("data/session_contexts")
DEFAULT_WORKSPACE_ROOT = Path("data/workspace")


def build_sdk_session_id(route_id: str, chatbot_name: str) -> str:
    """Build the runtime SDK session identifier for a route/chatbot pair."""
    return f"{route_id.replace(':', '-')}__{chatbot_name}"


def split_route_id(route_id: str) -> tuple[str, str]:
    """Split canonical route_id into platform and conversation_id."""
    platform, sep, conversation_id = route_id.rpartition(":")
    if not sep or not platform or not conversation_id:
        raise ValueError(f"Invalid route_id: {route_id}")
    return platform, conversation_id


def get_session_context(invocation: Mapping[str, Any]) -> SessionContext:
    """Extract structured session context from a tool invocation."""
    raw = invocation.get("session_context")
    if isinstance(raw, SessionContext):
        return raw
    if isinstance(raw, Mapping):
        return SessionContext.model_validate(dict(raw))

    route_id = invocation.get("route_id")
    if isinstance(route_id, str) and route_id:
        platform, conversation_id = split_route_id(route_id)
        return SessionContext(
            sdk_session_id=str(invocation.get("session_id", "")),
            route_id=route_id,
            platform=platform,
            conversation_id=conversation_id,
            chatbot_name=str(invocation.get("chatbot_name", "")),
        )

    session_id = invocation.get("session_id", "")
    raise RuntimeError(
        f"Missing session_context for session '{session_id}'"
    )


class SessionContextRegistry:
    """Runtime registry backed by optional persisted session metadata."""

    def __init__(
        self,
        metadata_dir: str | Path | None = None,
    ) -> None:
        self._metadata_dir = (
            Path(metadata_dir)
            if metadata_dir is not None
            else SESSION_CONTEXT_METADATA_DIR
        )
        self._contexts: dict[str, SessionContext] = {}

    def register(
        self,
        context: SessionContext,
        *,
        workdir: str | Path | None = None,
        persist_metadata: bool = True,
    ) -> None:
        self._contexts[context.sdk_session_id] = context
        if persist_metadata:
            self._persist_context(context, workdir=workdir)

    def resolve(self, sdk_session_id: str) -> SessionContext | None:
        if not sdk_session_id:
            return None
        context = self._contexts.get(sdk_session_id)
        if context is not None:
            return context

        path = self._metadata_path(sdk_session_id)
        if not path.exists():
            return None

        context = SessionContext.model_validate_json(
            path.read_text(encoding="utf-8")
        )
        self._contexts[sdk_session_id] = context
        return context

    def unregister(
        self,
        sdk_session_id: str,
        *,
        delete_metadata: bool = False,
    ) -> None:
        self._contexts.pop(sdk_session_id, None)
        if delete_metadata:
            path = self._metadata_path(sdk_session_id)
            if path.exists():
                path.unlink()

    def list_contexts(self) -> list[SessionContext]:
        """List persisted/known contexts for admin views."""
        known: dict[str, SessionContext] = {}
        if self._metadata_dir.exists():
            for path in sorted(self._metadata_dir.glob("*.json")):
                context = SessionContext.model_validate_json(
                    path.read_text(encoding="utf-8")
                )
                known.setdefault(context.sdk_session_id, context)
                self._contexts.setdefault(context.sdk_session_id, context)
        for session_id, context in self._contexts.items():
            if self._metadata_path(session_id).exists():
                known.setdefault(session_id, context)
        return list(known.values())

    def scan_workspace_sidecars(
        self,
        workspace_root: str | Path | None = None,
    ) -> list[SessionContext]:
        """Read legacy/default workspace sidecar files for route admin views."""
        root = Path(workspace_root) if workspace_root is not None else DEFAULT_WORKSPACE_ROOT
        contexts: list[SessionContext] = []
        if not root.exists():
            return contexts
        for path in sorted(root.glob(f"*/{SESSION_CONTEXT_FILENAME}")):
            context = SessionContext.model_validate_json(
                path.read_text(encoding="utf-8")
            )
            self._contexts.setdefault(context.sdk_session_id, context)
            contexts.append(context)
        return contexts

    def _persist_context(
        self,
        context: SessionContext,
        *,
        workdir: str | Path | None = None,
    ) -> None:
        payload = json.dumps(
            context.model_dump(),
            ensure_ascii=False,
            indent=2,
        )
        self._metadata_dir.mkdir(parents=True, exist_ok=True)
        self._metadata_path(context.sdk_session_id).write_text(
            payload,
            encoding="utf-8",
        )

        if workdir:
            sidecar = Path(workdir) / SESSION_CONTEXT_FILENAME
            sidecar.parent.mkdir(parents=True, exist_ok=True)
            sidecar.write_text(payload, encoding="utf-8")

    def _metadata_path(self, sdk_session_id: str) -> Path:
        return self._metadata_dir / f"{sdk_session_id}.json"
