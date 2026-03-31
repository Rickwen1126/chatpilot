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
from chatpilot.pipeline.samples.schedule_agent import ScheduleAgentNode
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


class _StubSdkSession:
    def __init__(self, session_id: str, tools: list, seen: dict) -> None:
        self._session_id = session_id
        self._tools = tools
        self._seen = seen

    async def send_and_wait(self, prompt: str, timeout: float = 300.0) -> str:
        self._seen["prompt"] = prompt
        self._seen["timeout"] = timeout
        if self._tools:
            result = await self._tools[0].handler({
                "session_id": self._session_id,
                "arguments": {},
            })
            self._seen["tool_result"] = result
        return "delegate ok"

    async def destroy(self) -> None:
        self._seen["destroyed"] = True


class _StubSdkClient:
    def __init__(self, seen: dict) -> None:
        self._seen = seen

    async def create_session(self, session_id: str, **kwargs):
        self._seen["session_id"] = session_id
        self._seen["tools"] = kwargs.get("tools") or []
        self._seen["working_directory"] = kwargs.get("working_directory")
        return _StubSdkSession(session_id, self._seen["tools"], self._seen)


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


def test_registry_list_contexts_ignores_non_persisted_sessions(tmp_path):
    registry = SessionContextRegistry(metadata_dir=tmp_path / "session-contexts")
    _register_context(registry, "line-webric-Ufc68__buddy")

    assert len(registry.list_contexts()) == 1

    registry.register(
        SessionContext(
            sdk_session_id="schedule-agent-ephemeral",
            route_id="line:webric:Ufc68",
            platform="line:webric",
            conversation_id="Ufc68",
            chatbot_name="buddy",
        ),
        persist_metadata=False,
    )

    listed_ids = {context.sdk_session_id for context in registry.list_contexts()}
    assert listed_ids == {"line-webric-Ufc68__buddy"}


@pytest.mark.asyncio
async def test_schedule_agent_registers_ephemeral_session_context(tmp_path):
    seen: dict = {"session_contexts": []}

    async def handler(invocation):
        seen["session_contexts"].append(invocation.get("session_context"))
        return {"resultType": "success", "textResultForLlm": "ok"}

    registry = SessionContextRegistry(metadata_dir=tmp_path / "session-contexts")
    factory = ToolFactory(session_context_registry=registry)
    factory.register(ToolDefinition(
        name="inspect_context",
        description="inspect context",
        parameters={"type": "object", "properties": {}},
        handler=handler,
        access_level=AccessLevel.GLOBAL,
    ))

    node = ScheduleAgentNode(
        sdk_client=_StubSdkClient(seen),
        tool_factory=factory,
    )

    result = await node.execute({
        "description": "run delegated task",
        "route_id": "line:webric:Ufc68",
        "chatbot_name": "buddy",
        "chatbot_tools": ["inspect_context"],
    })

    assert result.status == "success"
    assert seen["session_contexts"] == [{
        "sdk_session_id": seen["session_id"],
        "route_id": "line:webric:Ufc68",
        "platform": "line:webric",
        "conversation_id": "Ufc68",
        "chatbot_name": "buddy",
    }]
    assert registry.resolve(seen["session_id"]) is None
    assert registry.list_contexts() == []
    metadata_dir = tmp_path / "session-contexts"
    assert not metadata_dir.exists() or list(metadata_dir.glob("*.json")) == []


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
