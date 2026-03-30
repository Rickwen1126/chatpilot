"""Tests for SessionContext registry and resolver integration."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from chatpilot.core.types import (
    AccessLevel,
    SessionContext,
    ToolDefinition,
)
from chatpilot.server.webhook import router
from chatpilot.tools.builtin.query_observations import (
    create_query_observations_tool,
)
from chatpilot.tools.builtin.submit_task import create_submit_task_tool
from chatpilot.tools.factory import ToolFactory
from chatpilot.tools.session_context import SessionContextRegistry


class _StubMemoryStore:
    def __init__(self) -> None:
        self.queries: list[tuple[str, int, str]] = []

    async def query_observations(
        self, route_id: str, *, days: int, category: str
    ) -> list[dict]:
        self.queries.append((route_id, days, category))
        return [{
            "entries": [{
                "who": "阿明",
                "category": "進度",
                "content": "已完成",
                "timestamp": "2026-03-30T09:00:00Z",
            }]
        }]


class _StubScheduler:
    def __init__(self) -> None:
        self.enqueued = []

    async def enqueue(self, task) -> None:
        self.enqueued.append(task)


def _register_context(registry: SessionContextRegistry, session_id: str) -> None:
    registry.register(SessionContext(
        sdk_session_id=session_id,
        route_id="line:webric:Ufc68",
        platform="line:webric",
        conversation_id="Ufc68",
        chatbot_name="buddy",
    ))


@pytest.mark.asyncio
async def test_tool_factory_injects_resolved_session_context():
    registry = SessionContextRegistry()
    session_id = "line-webric-Ufc68__buddy"
    _register_context(registry, session_id)
    seen = {}

    async def handler(invocation):
        seen["session_context"] = invocation.get("session_context")
        return {"resultType": "success", "textResultForLlm": "ok"}

    factory = ToolFactory(session_context_registry=registry)
    factory.register(ToolDefinition(
        name="inspect_context",
        description="inspect context",
        parameters={"type": "object", "properties": {}},
        handler=handler,
        access_level=AccessLevel.GLOBAL,
    ))

    sdk_tool = factory.get_tools_for_chatbot(["inspect_context"])[0]
    result = await sdk_tool.handler({
        "session_id": session_id,
        "arguments": {},
    })

    assert result["resultType"] == "success"
    assert seen["session_context"] is not None
    assert seen["session_context"]["route_id"] == "line:webric:Ufc68"


@pytest.mark.asyncio
async def test_query_observations_uses_session_context_for_permissions():
    registry = SessionContextRegistry()
    session_id = "line-webric-Ufc68__buddy"
    _register_context(registry, session_id)
    memory_store = _StubMemoryStore()

    factory = ToolFactory(session_context_registry=registry)
    factory.register(create_query_observations_tool(
        memory_store,
        {
            "Main Group": {
                "route_id": "line:Csource",
                "allowed_consumers": ["line:Ufc68"],
            }
        },
    ))

    sdk_tool = factory.get_tools_for_chatbot(["query_observations"])[0]
    result = await sdk_tool.handler({
        "session_id": session_id,
        "arguments": {"source": "Main Group"},
    })

    assert result["resultType"] == "success"
    assert memory_store.queries == [("line:Csource", 7, "")]


@pytest.mark.asyncio
async def test_submit_task_uses_route_id_from_session_context():
    registry = SessionContextRegistry()
    session_id = "line-webric-Ufc68__buddy"
    _register_context(registry, session_id)
    scheduler = _StubScheduler()

    factory = ToolFactory(session_context_registry=registry)
    factory.register(create_submit_task_tool(scheduler))
    sdk_tool = factory.get_tools_for_chatbot(["submit_task"])[0]

    await sdk_tool.handler({
        "session_id": session_id,
        "arguments": {"task_description": "do work"},
    })

    assert scheduler.enqueued[0].chat_route_id == "line:webric:Ufc68"


def test_cli_routes_reads_workspace_session_context_metadata(
    monkeypatch, tmp_path
):
    monkeypatch.chdir(tmp_path)
    workdir = tmp_path / "data" / "workspace" / "line-webric-C123__buddy"
    workdir.mkdir(parents=True)
    (workdir / "session_context.json").write_text(
        json.dumps({
            "sdk_session_id": "line-webric-C123__buddy",
            "route_id": "line:webric:C123",
            "platform": "line:webric",
            "conversation_id": "C123",
            "chatbot_name": "buddy",
        }),
        encoding="utf-8",
    )

    app = FastAPI()
    app.include_router(router)
    app.state.chatbot_manager = SimpleNamespace(
        get_current_chatbot=lambda route_id: None,
    )
    app.state.binding_router = SimpleNamespace(_bindings=[])

    client = TestClient(app)
    response = client.get("/cli/routes")

    assert response.status_code == 200
    assert response.json()["routes"] == [{
        "route_id": "line:webric:C123",
        "label": None,
        "platform": "line:webric",
        "conversation_id": "C123",
        "current_chatbot": "buddy",
        "override": None,
        "default_binding": None,
        "sessions": ["buddy"],
    }]
