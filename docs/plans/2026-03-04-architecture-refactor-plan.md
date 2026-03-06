# Architecture Refactor Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Refactor ChatPilot from hardcoded `/倉管` + keyword routing into a clean pipeline with conversation-centric `routes.yaml`, `/agent` command, and separated `MessageProcessor`.

**Architecture:** Extract business logic from `webhook.py` into `MessageProcessor`. Replace keyword-based dispatcher with simple dict lookup on `conversationRoutes`. Add unified `CommandHandler` for `/model` and `/agent`. Delete dispatcher.py.

**Tech Stack:** Python 3.11+ / FastAPI / Pydantic v2 / pytest / ruff / uv

---

### Task 1: New Route Types in core/types.py

**Files:**
- Modify: `src/chatpilot/core/types.py`
- Test: `tests/unit/test_route_config.py`

**Step 1: Write the failing test**

Create `tests/unit/test_route_config.py`:

```python
"""Unit tests for RouteConfig schema."""

import os
import tempfile

import yaml

from chatpilot.core.types import ConversationRoute, PlatformConfig, RouteConfig


def test_conversation_route_basic():
    route = ConversationRoute(agent="general-agent", model="gpt-4.1", workdir="~/code")
    assert route.agent == "general-agent"
    assert route.model == "gpt-4.1"
    assert route.workdir == "~/code"


def test_conversation_route_defaults():
    route = ConversationRoute(agent="general-agent")
    assert route.model is None
    assert route.workdir is None


def test_platform_config_from_dict():
    data = {
        "defaultAgent": "general-agent",
        "conversationRoutes": {
            "null": {"agent": "general-agent", "model": "claude-haiku-4.5"},
        },
    }
    config = PlatformConfig.model_validate(data)
    assert config.default_agent == "general-agent"
    assert "null" in config.conversation_routes
    assert config.conversation_routes["null"].agent == "general-agent"


def test_route_config_from_yaml():
    yaml_str = """
agentList:
  - general-agent
  - warehouse-agent
platforms:
  line:
    defaultAgent: general-agent
    conversationRoutes:
      "null":
        agent: general-agent
        model: claude-haiku-4.5
        workdir: ~/code/chatpilot/
  mock:
    defaultAgent: general-agent
    conversationRoutes:
      "null":
        agent: general-agent
        model: gpt-4.1
"""
    data = yaml.safe_load(yaml_str)
    config = RouteConfig.model_validate(data)
    assert config.agent_list == ["general-agent", "warehouse-agent"]
    assert "line" in config.platforms
    assert config.platforms["line"].default_agent == "general-agent"
    null_route = config.platforms["line"].conversation_routes["null"]
    assert null_route.agent == "general-agent"
    assert null_route.model == "claude-haiku-4.5"
    assert null_route.workdir == "~/code/chatpilot/"


def test_route_config_empty_conversation_routes():
    data = {
        "agentList": ["general-agent"],
        "platforms": {
            "line": {"defaultAgent": "general-agent"},
        },
    }
    config = RouteConfig.model_validate(data)
    assert config.platforms["line"].conversation_routes == {}
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_route_config.py -v`
Expected: FAIL — `ImportError: cannot import name 'ConversationRoute'`

**Step 3: Write the new types**

Add to `src/chatpilot/core/types.py` (keep all existing types for now — they'll be removed in Task 7):

```python
class ConversationRoute(BaseModel):
    """Per-conversation routing config."""
    agent: str
    model: str | None = None
    workdir: str | None = None


class PlatformConfig(BaseModel):
    """Per-platform config with default agent and conversation routes."""
    default_agent: str = Field(alias="defaultAgent")
    conversation_routes: dict[str, ConversationRoute] = Field(
        default_factory=dict, alias="conversationRoutes"
    )

    model_config = {"populate_by_name": True}


class RouteConfig(BaseModel):
    """Top-level route configuration."""
    agent_list: list[str] = Field(alias="agentList")
    platforms: dict[str, PlatformConfig]

    model_config = {"populate_by_name": True}
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_route_config.py -v`
Expected: All 5 tests PASS

**Step 5: Commit**

```bash
git add src/chatpilot/core/types.py tests/unit/test_route_config.py
git commit -m "feat: add RouteConfig/PlatformConfig/ConversationRoute types"
```

---

### Task 2: Update route_loader.py for new schema

**Files:**
- Modify: `src/chatpilot/dispatch/route_loader.py`
- Modify: `tests/unit/test_route_loader.py`

**Step 1: Write the failing tests**

Replace `tests/unit/test_route_loader.py` entirely:

```python
"""Unit tests for route loader — new RouteConfig schema."""

import os
import tempfile

from chatpilot.dispatch.route_loader import load_route_config, save_route_config


def test_load_route_config_valid():
    yaml_content = """
agentList:
  - general-agent
  - warehouse-agent
platforms:
  line:
    defaultAgent: general-agent
    conversationRoutes:
      "null":
        agent: general-agent
        model: claude-haiku-4.5
        workdir: ~/code/chatpilot/
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(yaml_content)
        f.flush()
        config = load_route_config(f.name)
    os.unlink(f.name)

    assert config.agent_list == ["general-agent", "warehouse-agent"]
    assert config.platforms["line"].default_agent == "general-agent"
    null_route = config.platforms["line"].conversation_routes["null"]
    assert null_route.agent == "general-agent"
    assert null_route.model == "claude-haiku-4.5"


def test_load_route_config_empty():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write("")
        f.flush()
        config = load_route_config(f.name)
    os.unlink(f.name)

    assert config.agent_list == []
    assert config.platforms == {}


def test_save_and_reload():
    yaml_content = """
agentList:
  - general-agent
platforms:
  mock:
    defaultAgent: general-agent
    conversationRoutes:
      "null":
        agent: general-agent
        model: gpt-4.1
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(yaml_content)
        f.flush()
        path = f.name

    config = load_route_config(path)
    # Modify and save
    config.platforms["mock"].conversation_routes["null"].model = "claude-haiku-4.5"
    save_route_config(path, config)

    # Reload and verify
    reloaded = load_route_config(path)
    assert reloaded.platforms["mock"].conversation_routes["null"].model == "claude-haiku-4.5"

    os.unlink(path)
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_route_loader.py -v`
Expected: FAIL — `ImportError: cannot import name 'load_route_config'`

**Step 3: Update route_loader.py**

In `src/chatpilot/dispatch/route_loader.py`, add `load_route_config` and `save_route_config` functions alongside existing `load_routes`/`save_routes` (keep old functions for now — removed in Task 7). Also update `RouteWatcher` to support the new config:

```python
from chatpilot.core.types import RouteConfig

def load_route_config(path: str) -> RouteConfig:
    """Load and validate routes from YAML using new RouteConfig schema."""
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
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_route_loader.py -v`
Expected: All 3 tests PASS

**Step 5: Commit**

```bash
git add src/chatpilot/dispatch/route_loader.py tests/unit/test_route_loader.py
git commit -m "feat: add load_route_config/save_route_config for new schema"
```

---

### Task 3: CommandHandler with /agent and /model

**Files:**
- Create: `src/chatpilot/processing/__init__.py`
- Create: `src/chatpilot/processing/command_handler.py`
- Test: `tests/unit/test_command_handler.py`

**Step 1: Write the failing tests**

Create `tests/unit/test_command_handler.py`:

```python
"""Unit tests for CommandHandler — /agent and /model commands."""

import os
import tempfile

import yaml

from chatpilot.core.types import (
    ConversationRoute,
    Message,
    PlatformConfig,
    RouteConfig,
)
from chatpilot.processing.command_handler import CommandHandler


def _make_config() -> RouteConfig:
    return RouteConfig(
        agent_list=["general-agent", "warehouse-agent"],
        platforms={
            "line": PlatformConfig(
                default_agent="general-agent",
                conversation_routes={
                    "null": ConversationRoute(
                        agent="general-agent",
                        model="claude-haiku-4.5",
                    ),
                },
            ),
        },
    )


def _make_msg(text: str, conversation_id: str | None = None) -> Message:
    return Message(
        text=text,
        user_id="U123",
        platform="line",
        conversation_id=conversation_id,
    )


def test_not_a_command():
    handler = CommandHandler()
    config = _make_config()
    result = handler.try_handle(_make_msg("hello"), config, "")
    assert result is None


def test_agent_list():
    handler = CommandHandler()
    config = _make_config()
    result = handler.try_handle(_make_msg("/agent"), config, "")
    assert result is not None
    assert "general-agent" in result
    assert "warehouse-agent" in result


def test_agent_switch():
    handler = CommandHandler()
    config = _make_config()
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(config.model_dump(by_alias=True), f)
        path = f.name

    result = handler.try_handle(_make_msg("/agent warehouse"), config, path)
    assert result is not None
    assert "warehouse" in result.lower()
    # Verify the config was updated in-memory
    assert config.platforms["line"].conversation_routes["null"].agent == "warehouse-agent"

    os.unlink(path)


def test_agent_switch_unknown():
    handler = CommandHandler()
    config = _make_config()
    result = handler.try_handle(_make_msg("/agent unknown-agent"), config, "")
    assert result is not None
    assert "找不到" in result


def test_model_show_current():
    handler = CommandHandler()
    config = _make_config()
    result = handler.try_handle(_make_msg("/model"), config, "")
    assert result is not None
    assert "claude-haiku-4.5" in result


def test_model_switch():
    handler = CommandHandler()
    config = _make_config()
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(config.model_dump(by_alias=True), f)
        path = f.name

    result = handler.try_handle(_make_msg("/model sonnet"), config, path)
    assert result is not None
    assert "claude-sonnet-4.6" in result
    assert config.platforms["line"].conversation_routes["null"].model == "claude-sonnet-4.6"

    os.unlink(path)
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_command_handler.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'chatpilot.processing'`

**Step 3: Create the package and CommandHandler**

Create `src/chatpilot/processing/__init__.py`:
```python
"""Processing module — message processor and command handler."""
```

Create `src/chatpilot/processing/command_handler.py`:

```python
"""CommandHandler — instant slash commands (/model, /agent)."""

from __future__ import annotations

import logging

from chatpilot.core.types import ConversationRoute, Message, RouteConfig
from chatpilot.dispatch.route_loader import save_route_config

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gpt-4.1"

MODEL_ALIASES: dict[str, str] = {
    "gpt-4.1": "gpt-4.1",
    "gpt-5-mini": "gpt-5-mini",
    "gpt-5.1": "gpt-5.1",
    "gpt-5.2": "gpt-5.2",
    "claude-haiku-4.5": "claude-haiku-4.5",
    "claude-sonnet-4": "claude-sonnet-4",
    "claude-sonnet-4.5": "claude-sonnet-4.5",
    "claude-sonnet-4.6": "claude-sonnet-4.6",
    "claude-opus-4.5": "claude-opus-4.5",
    "claude-opus-4.6": "claude-opus-4.6",
    "gemini-3-pro-preview": "gemini-3-pro-preview",
    "4.1": "gpt-4.1",
    "5mini": "gpt-5-mini",
    "5.1": "gpt-5.1",
    "5.2": "gpt-5.2",
    "haiku": "claude-haiku-4.5",
    "sonnet": "claude-sonnet-4.6",
    "sonnet4": "claude-sonnet-4",
    "sonnet4.5": "claude-sonnet-4.5",
    "sonnet4.6": "claude-sonnet-4.6",
    "opus": "claude-opus-4.6",
    "opus4.5": "claude-opus-4.5",
    "opus4.6": "claude-opus-4.6",
    "gemini": "gemini-3-pro-preview",
}

AVAILABLE_MODELS = sorted(set(MODEL_ALIASES.values()))


def _fuzzy_match_model(user_input: str) -> str | None:
    normalized = user_input.lower().strip()
    if not normalized:
        return None
    if normalized in MODEL_ALIASES:
        return MODEL_ALIASES[normalized]
    for model_id in AVAILABLE_MODELS:
        if normalized in model_id:
            return model_id
    return None


class CommandHandler:
    """Handles instant slash commands. Bypasses session gate."""

    def try_handle(
        self,
        msg: Message,
        route_config: RouteConfig,
        routes_path: str,
    ) -> str | None:
        """Returns reply text if msg is a command, None otherwise."""
        text = msg.text.strip()
        if text.lower().startswith("/model"):
            return self._handle_model(text, msg, route_config, routes_path)
        if text.lower().startswith("/agent"):
            return self._handle_agent(text, msg, route_config, routes_path)
        return None

    def _get_conversation_key(self, msg: Message) -> str:
        return msg.conversation_id or "null"

    def _get_route(
        self, msg: Message, route_config: RouteConfig
    ) -> ConversationRoute | None:
        platform_config = route_config.platforms.get(msg.platform)
        if not platform_config:
            return None
        key = self._get_conversation_key(msg)
        return platform_config.conversation_routes.get(key)

    def _ensure_route(
        self, msg: Message, route_config: RouteConfig
    ) -> ConversationRoute:
        """Get or create a ConversationRoute for this conversation."""
        platform_config = route_config.platforms.get(msg.platform)
        if not platform_config:
            return ConversationRoute(agent="general-agent")
        key = self._get_conversation_key(msg)
        route = platform_config.conversation_routes.get(key)
        if route is None:
            route = ConversationRoute(agent=platform_config.default_agent)
            platform_config.conversation_routes[key] = route
        return route

    def _handle_agent(
        self,
        text: str,
        msg: Message,
        route_config: RouteConfig,
        routes_path: str,
    ) -> str:
        parts = text.strip().split(maxsplit=1)
        route = self._get_route(msg, route_config)
        current_agent = route.agent if route else "unknown"

        if len(parts) == 1:
            available = ", ".join(route_config.agent_list)
            return f"目前 Agent：{current_agent}\n可用：{available}"

        requested = parts[1].strip().lower()

        # Fuzzy match against agent_list
        matched = None
        for name in route_config.agent_list:
            if requested == name or requested in name:
                matched = name
                break

        if matched is None:
            available = ", ".join(route_config.agent_list)
            return f"找不到 Agent「{parts[1].strip()}」\n可用：{available}"

        route = self._ensure_route(msg, route_config)
        route.agent = matched
        if routes_path:
            save_route_config(routes_path, route_config)
        logger.info("Agent switched to %s for %s/%s", matched, msg.platform, msg.conversation_id)
        return f"Agent 已切換為：{matched} ✓"

    def _handle_model(
        self,
        text: str,
        msg: Message,
        route_config: RouteConfig,
        routes_path: str,
    ) -> str:
        parts = text.strip().split(maxsplit=1)
        route = self._get_route(msg, route_config)
        current_model = (route.model if route else None) or DEFAULT_MODEL

        if len(parts) == 1:
            return f"目前使用的模型：{current_model}"

        matched = _fuzzy_match_model(parts[1])
        if matched is None:
            available = ", ".join(AVAILABLE_MODELS)
            return f"找不到匹配的模型「{parts[1]}」\n可用：{available}"

        route = self._ensure_route(msg, route_config)
        route.model = matched
        if routes_path:
            save_route_config(routes_path, route_config)
        logger.info("Model switched to %s for %s/%s", matched, msg.platform, msg.conversation_id)
        return f"模型已切換為：{matched} ✓"
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_command_handler.py -v`
Expected: All 6 tests PASS

**Step 5: Commit**

```bash
git add src/chatpilot/processing/__init__.py src/chatpilot/processing/command_handler.py tests/unit/test_command_handler.py
git commit -m "feat: add CommandHandler with /agent and /model commands"
```

---

### Task 4: Add workdir to BaseAgent Protocol

**Files:**
- Modify: `src/chatpilot/agents/base.py`
- Modify: `src/chatpilot/agents/general/__init__.py`
- Modify: `src/chatpilot/agents/warehouse/__init__.py`
- Modify: `tests/conftest.py` (StubAgent)

**Step 1: Update BaseAgent Protocol**

In `src/chatpilot/agents/base.py`, change `handle` signature:

```python
@runtime_checkable
class BaseAgent(Protocol):
    @property
    def name(self) -> str: ...

    async def handle(
        self, message: Message, session_id: str,
        model: str | None = None, workdir: str | None = None,
    ) -> Response: ...
```

**Step 2: Update GeneralAgent**

In `src/chatpilot/agents/general/__init__.py`, add `workdir` param to `handle`:

```python
async def handle(
    self, message: Message, session_id: str,
    model: str | None = None, workdir: str | None = None,
) -> Response:
```

(No behavior change — just accepts and ignores `workdir` for now.)

**Step 3: Update WarehouseAgent**

In `src/chatpilot/agents/warehouse/__init__.py`, add `workdir` param to `handle`:

```python
async def handle(
    self, message: Message, session_id: str,
    model: str | None = None, workdir: str | None = None,
) -> Response:
```

**Step 4: Update StubAgent in conftest.py**

In `tests/conftest.py`, update `StubAgent.handle`:

```python
async def handle(self, message, session_id: str, model: str | None = None, workdir: str | None = None):
    return Response(text=f"[{self._name}] reply")
```

**Step 5: Run all tests**

Run: `uv run pytest -v`
Expected: All existing tests PASS

**Step 6: Commit**

```bash
git add src/chatpilot/agents/base.py src/chatpilot/agents/general/__init__.py src/chatpilot/agents/warehouse/__init__.py tests/conftest.py
git commit -m "feat: add workdir param to BaseAgent.handle() Protocol"
```

---

### Task 5: MessageProcessor

**Files:**
- Create: `src/chatpilot/processing/processor.py`
- Test: `tests/unit/test_processor.py`

**Step 1: Write the failing tests**

Create `tests/unit/test_processor.py`:

```python
"""Unit tests for MessageProcessor."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from chatpilot.core.types import (
    ConversationRoute,
    Message,
    PlatformConfig,
    Response,
    RouteConfig,
)
from chatpilot.processing.processor import MessageProcessor


def _make_config() -> RouteConfig:
    return RouteConfig(
        agent_list=["general-agent", "warehouse-agent"],
        platforms={
            "mock": PlatformConfig(
                default_agent="general-agent",
                conversation_routes={
                    "null": ConversationRoute(
                        agent="general-agent",
                        model="gpt-4.1",
                        workdir="~/code",
                    ),
                    "c1": ConversationRoute(
                        agent="warehouse-agent",
                        model="claude-haiku-4.5",
                    ),
                },
            ),
        },
    )


def _make_msg(text: str = "hello", conversation_id: str | None = None) -> Message:
    return Message(
        text=text,
        user_id="U1",
        platform="mock",
        conversation_id=conversation_id,
    )


def _make_agent(name: str = "general-agent", response_text: str = "ok") -> MagicMock:
    agent = MagicMock()
    agent.name = name
    agent.handle = AsyncMock(return_value=Response(text=response_text))
    return agent


def _make_adapter() -> MagicMock:
    adapter = MagicMock()
    adapter.send_response = AsyncMock()
    adapter.send_processing_ack = AsyncMock()
    return adapter


@pytest.mark.asyncio
async def test_command_handled():
    """Slash commands should be handled by CommandHandler, not reach the agent."""
    config = _make_config()
    agent = _make_agent()
    agents = {"general-agent": agent}
    processor = MessageProcessor(config, "", agents, timeout_s=20.0)

    adapter = _make_adapter()
    msg = _make_msg("/agent")

    await processor.process(msg, adapter)

    adapter.send_response.assert_called_once()
    reply = adapter.send_response.call_args[0][1].text
    assert "general-agent" in reply
    agent.handle.assert_not_called()


@pytest.mark.asyncio
async def test_route_to_default_agent():
    """Private chat with null route should go to general-agent."""
    config = _make_config()
    agent = _make_agent("general-agent", "hi there")
    agents = {"general-agent": agent}
    processor = MessageProcessor(config, "", agents, timeout_s=20.0)

    adapter = _make_adapter()
    msg = _make_msg("hello")  # conversation_id=None → key="null"

    await processor.process(msg, adapter)

    agent.handle.assert_called_once()
    call_kwargs = agent.handle.call_args
    assert call_kwargs[1].get("model") == "gpt-4.1" or call_kwargs[0][3] if len(call_kwargs[0]) > 3 else True
    adapter.send_response.assert_called_once()


@pytest.mark.asyncio
async def test_route_to_conversation_agent():
    """Message to conversation c1 should go to warehouse-agent."""
    config = _make_config()
    wh_agent = _make_agent("warehouse-agent", "inventory data")
    agents = {"warehouse-agent": wh_agent, "general-agent": _make_agent()}
    processor = MessageProcessor(config, "", agents, timeout_s=20.0)

    adapter = _make_adapter()
    msg = _make_msg("查庫存", conversation_id="c1")

    await processor.process(msg, adapter)

    wh_agent.handle.assert_called_once()


@pytest.mark.asyncio
async def test_unknown_platform_ignored():
    """Message from unregistered platform should be silently ignored."""
    config = _make_config()
    processor = MessageProcessor(config, "", {}, timeout_s=20.0)

    adapter = _make_adapter()
    msg = Message(text="hello", user_id="U1", platform="telegram", conversation_id=None)

    await processor.process(msg, adapter)

    adapter.send_response.assert_not_called()


@pytest.mark.asyncio
async def test_gate_blocks_concurrent():
    """Second message while first is processing should be blocked by gate."""
    config = _make_config()

    # Agent that takes 1 second
    slow_agent = MagicMock()
    slow_agent.name = "general-agent"

    async def slow_handle(*args, **kwargs):
        await asyncio.sleep(1)
        return Response(text="done")

    slow_agent.handle = slow_handle
    agents = {"general-agent": slow_agent}
    processor = MessageProcessor(config, "", agents, timeout_s=5.0)

    adapter = _make_adapter()
    msg1 = _make_msg("first")
    msg2 = _make_msg("second")

    # Start first message processing (don't await)
    task = asyncio.create_task(processor.process(msg1, adapter))
    await asyncio.sleep(0.05)  # Let it acquire the gate

    # Second message should be gated
    await processor.process(msg2, adapter)

    # Second call should get "處理中" response
    calls = adapter.send_response.call_args_list
    assert any("處理中" in str(call) for call in calls)

    await task
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_processor.py -v`
Expected: FAIL — `ImportError: cannot import name 'MessageProcessor'`

**Step 3: Write MessageProcessor**

Create `src/chatpilot/processing/processor.py`:

```python
"""MessageProcessor — platform-agnostic message processing pipeline."""

from __future__ import annotations

import asyncio
import logging
import time

from chatpilot.channels.adapter import ChannelAdapter
from chatpilot.core.types import Message, Response, RouteConfig
from chatpilot.processing.command_handler import CommandHandler
from chatpilot.queue.pending_queue import pending_queue
from chatpilot.sdk.session_manager import SessionManager
from chatpilot.server.session_gate import session_gate

logger = logging.getLogger(__name__)


def _log(conversation_id: str | None, category: str, detail: str) -> None:
    ts = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
    cid = conversation_id or "private"
    print(f"[{ts}] [{cid}] {category} {detail}", flush=True)


class MessageProcessor:
    """Platform-agnostic message processing pipeline.

    Pipeline: command check → gate → resolve route → agent handle → respond
    """

    def __init__(
        self,
        route_config: RouteConfig,
        routes_path: str,
        agents: dict,
        timeout_s: float = 20.0,
    ) -> None:
        self.route_config = route_config
        self.routes_path = routes_path
        self.agents = agents
        self.timeout_s = timeout_s
        self.command_handler = CommandHandler()

    async def process(self, msg: Message, adapter: ChannelAdapter) -> None:
        session_id = SessionManager.get_session_id(
            msg.platform, msg.conversation_id, msg.user_id
        )

        _log(msg.conversation_id, "RECV", f'platform={msg.platform} text="{msg.text}"')

        # 1. Commands — instant, no gate
        reply = self.command_handler.try_handle(msg, self.route_config, self.routes_path)
        if reply is not None:
            _log(msg.conversation_id, "CMD", f'"{reply[:80]}"')
            await adapter.send_response(msg, Response(text=reply))
            return

        # 2. Gate check
        if session_gate.is_busy(session_id):
            session_gate.queue(session_id, msg.text)
            _log(msg.conversation_id, "GATE", "session busy, queued message")
            await adapter.send_response(msg, Response(text="目前正在處理中，請稍候…"))
            return

        session_gate.acquire(session_id)
        bg = False
        try:
            bg = await self._handle_with_agent(msg, adapter, session_id)
        except Exception:
            bg = False
            raise
        finally:
            if not bg:
                self._release_gate(session_id)

    async def _handle_with_agent(
        self,
        msg: Message,
        adapter: ChannelAdapter,
        session_id: str,
    ) -> bool:
        """Resolve route, handle with agent. Returns True if background task spawned."""
        agent_name, model, workdir = self._resolve_route(msg)
        agent = self.agents.get(agent_name)

        if agent is None:
            _log(msg.conversation_id, "ROUTE", f"agent not found: {agent_name}")
            return False

        _log(msg.conversation_id, "ROUTE", f"agent={agent_name} model={model}")

        # Collect pending messages
        pending_texts = self._collect_pending(session_id)

        try:
            response = await asyncio.wait_for(
                agent.handle(msg, session_id, model=model, workdir=workdir),
                timeout=self.timeout_s,
            )
            _log(
                msg.conversation_id,
                "AGENT",
                f'agent={agent_name} text="{response.text[:100]}"',
            )
            reply_text = self._combine_pending(pending_texts, response.text)
            await adapter.send_response(msg, Response(text=reply_text))
            return False
        except asyncio.TimeoutError:
            _log(msg.conversation_id, "TIMEOUT", f"agent={agent_name}")
            for text in pending_texts:
                pending_queue.enqueue(session_id, text)
            await adapter.send_processing_ack(msg)
            asyncio.create_task(
                self._background_handle(msg, agent, session_id, model=model)
            )
            return True
        except Exception as e:
            _log(msg.conversation_id, "ERROR", f"agent={agent_name} error={e}")
            error_text = "抱歉，處理時發生錯誤，請稍後再試。"
            if pending_texts:
                error_text = "\n\n".join(pending_texts) + "\n\n" + error_text
            await adapter.send_response(msg, Response(text=error_text))
            return False

    def _resolve_route(
        self, msg: Message
    ) -> tuple[str, str | None, str | None]:
        """Look up agent, model, workdir for a message."""
        platform_config = self.route_config.platforms.get(msg.platform)
        if not platform_config:
            return "general-agent", None, None
        key = msg.conversation_id or "null"
        route = platform_config.conversation_routes.get(key)
        if not route:
            return platform_config.default_agent, None, None
        return route.agent, route.model, route.workdir

    def _collect_pending(self, session_id: str) -> list[str]:
        texts: list[str] = []
        pending = pending_queue.dequeue(session_id)
        while pending is not None:
            texts.append(pending.content)
            pending = pending_queue.dequeue(session_id)
        return texts

    def _combine_pending(self, pending_texts: list[str], response_text: str) -> str:
        if pending_texts:
            return "\n\n".join(pending_texts) + "\n\n" + response_text
        return response_text

    def _release_gate(self, session_id: str) -> None:
        dropped = session_gate.release(session_id)
        if dropped:
            pending_queue.enqueue(
                session_id,
                f"（您稍早傳送的訊息「{dropped[:30]}」已略過，請重新發送）",
            )

    async def _background_handle(
        self, msg: Message, agent, session_id: str, model: str | None = None
    ) -> None:
        try:
            response = await agent.handle(msg, session_id, model=model)
            pending_queue.enqueue(session_id, response.text)
            _log(
                msg.conversation_id,
                "QUEUED",
                f'agent={agent.name} text="{response.text[:50]}..."',
            )
        except Exception as e:
            _log(msg.conversation_id, "ERROR", f"background handle failed: {e}")
        finally:
            self._release_gate(session_id)
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_processor.py -v`
Expected: All 5 tests PASS

**Step 5: Commit**

```bash
git add src/chatpilot/processing/processor.py tests/unit/test_processor.py
git commit -m "feat: add MessageProcessor with clean pipeline"
```

---

### Task 6: Wire up new architecture in server + thin webhook

**Files:**
- Modify: `src/chatpilot/server/__init__.py`
- Modify: `src/chatpilot/server/webhook.py`
- Modify: `config/routes.yaml`

**Step 1: Update config/routes.yaml to new format**

```yaml
agentList:
  - general-agent
  - warehouse-agent

platforms:
  line:
    defaultAgent: general-agent
    conversationRoutes:
      "null":
        agent: general-agent
        model: claude-haiku-4.5
        workdir: ~/code/chatpilot/
  mock:
    defaultAgent: general-agent
    conversationRoutes:
      "null":
        agent: general-agent
        model: gpt-4.1
        workdir: ~/code/chatpilot/
```

**Step 2: Update server/__init__.py**

Replace the lifespan to use `RouteConfig` and `MessageProcessor`:

- Replace `load_routes` with `load_route_config`
- Replace `route_map` with `route_config` on `app.state`
- Create `MessageProcessor` and store on `app.state.processor`
- Remove route_map validation (agentList is validated instead)
- Update `RouteWatcher` to use new config loader

Key changes in `lifespan()`:
```python
from chatpilot.dispatch.route_loader import load_route_config, RouteWatcher
from chatpilot.processing.processor import MessageProcessor

# Load routes (new schema)
route_config = load_route_config(routes_path)
app.state.route_config = route_config

# Validate agent names in agentList
for name in route_config.agent_list:
    if name not in agent_registry:
        raise RouteError(f"unknown agent in agentList: {name}")

# Create processor
timeout_s = int(os.environ.get("REPLY_TIMEOUT_MS", "20000")) / 1000.0
processor = MessageProcessor(route_config, routes_path, agent_registry, timeout_s)
app.state.processor = processor
```

**Step 3: Thin down webhook.py**

Replace entirely with:

```python
"""Webhook handler — POST /webhook/{platform} thin route."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response

from chatpilot.channels.adapter import AdapterRegistry

router = APIRouter()


@router.post("/webhook/{platform}")
async def webhook_handler(platform: str, request: Request) -> Response:
    """Handle incoming webhook from any platform."""
    app = request.app
    adapter_registry: AdapterRegistry = app.state.adapter_registry

    adapter = adapter_registry.get(platform)
    if adapter is None:
        return Response(status_code=400, content=f"Unknown platform: {platform}")

    raw_body = await request.body()
    signature = request.headers.get("x-line-signature", "")
    if not adapter.verify_signature(raw_body, signature):
        return Response(status_code=401, content="Invalid signature")

    if hasattr(adapter, "parse_messages_with_signature"):
        messages = adapter.parse_messages_with_signature(raw_body, signature)
    else:
        messages = adapter.parse_messages(raw_body)

    for msg in messages:
        await app.state.processor.process(msg, adapter)

    return Response(status_code=200, content="OK")
```

**Step 4: Run all tests**

Run: `uv run pytest -v`
Expected: Some old tests will fail (they reference old types/dispatcher) — that's expected, fixed in Task 7.

**Step 5: Commit**

```bash
git add config/routes.yaml src/chatpilot/server/__init__.py src/chatpilot/server/webhook.py
git commit -m "feat: wire MessageProcessor, thin webhook, new routes.yaml format"
```

---

### Task 7: Clean up — delete old dispatcher, old types, old tests

**Files:**
- Delete: `src/chatpilot/dispatch/dispatcher.py`
- Delete: `src/chatpilot/commands/model_command.py`
- Delete: `tests/unit/test_dispatcher.py`
- Modify: `src/chatpilot/core/types.py` — remove `KeywordMapping`, `KeywordMatch`, `FallbackMatch`, `Ignored`, `RouteRule`, `RouteMap`, `DispatchResult`
- Modify: `tests/conftest.py` — remove old fixture imports and `mock_route_map`
- Modify: `tests/integration/test_webhook.py` — update for new architecture

**Step 1: Delete old files**

```bash
rm src/chatpilot/dispatch/dispatcher.py
rm src/chatpilot/commands/model_command.py
rm tests/unit/test_dispatcher.py
```

**Step 2: Clean up types.py**

Remove these types from `src/chatpilot/core/types.py`:
- `KeywordMapping`
- `RouteRule`
- `RouteMap`
- `KeywordMatch`
- `FallbackMatch`
- `Ignored`
- `DispatchResult`

Keep: `Message`, `Attachment`, `Response`, `LinePlatformContext`, `PendingMessage`, `ConversationRoute`, `PlatformConfig`, `RouteConfig`, `Platform`

**Step 3: Update conftest.py**

Replace `tests/conftest.py`:

```python
"""Shared test fixtures."""

import pytest

from chatpilot.core.types import (
    ConversationRoute,
    LinePlatformContext,
    Message,
    PlatformConfig,
    Response,
    RouteConfig,
)


@pytest.fixture
def mock_message():
    return Message(
        text="你好",
        user_id="U123",
        platform="line",
        conversation_id="C456",
        platform_context=LinePlatformContext(
            reply_token="token123",
            message_id="msg789",
            timestamp=1700000000000,
        ),
    )


@pytest.fixture
def mock_private_message():
    return Message(
        text="你好",
        user_id="U123",
        platform="line",
        conversation_id=None,
    )


@pytest.fixture
def mock_response():
    return Response(text="Hello from agent!")


@pytest.fixture
def mock_route_config():
    return RouteConfig(
        agent_list=["general-agent", "warehouse-agent"],
        platforms={
            "line": PlatformConfig(
                default_agent="general-agent",
                conversation_routes={
                    "null": ConversationRoute(
                        agent="general-agent",
                        model="claude-haiku-4.5",
                    ),
                    "C456": ConversationRoute(
                        agent="general-agent",
                        model="claude-haiku-4.5",
                    ),
                },
            ),
        },
    )


@pytest.fixture
def mock_agent_registry():
    class StubAgent:
        def __init__(self, name: str):
            self._name = name

        @property
        def name(self) -> str:
            return self._name

        async def handle(
            self, message, session_id: str,
            model: str | None = None, workdir: str | None = None,
        ):
            return Response(text=f"[{self._name}] reply")

    return {
        "general-agent": StubAgent("general-agent"),
        "warehouse-agent": StubAgent("warehouse-agent"),
    }
```

**Step 4: Update webhook integration tests**

Replace `tests/integration/test_webhook.py`:

```python
"""Integration tests for webhook endpoint using mock adapter."""

import json

import pytest
from httpx import ASGITransport, AsyncClient

from chatpilot.core.types import (
    ConversationRoute,
    Message,
    PlatformConfig,
    Response,
    RouteConfig,
)


@pytest.fixture
def mock_app():
    from fastapi import FastAPI

    from chatpilot.agents import agent_registry, register_agent
    from chatpilot.channels.adapter import AdapterRegistry
    from chatpilot.channels.mock import mock_adapter
    from chatpilot.processing.processor import MessageProcessor
    from chatpilot.server.webhook import router

    app = FastAPI()
    app.include_router(router)

    adapter_registry: AdapterRegistry = {"mock": mock_adapter}
    app.state.adapter_registry = adapter_registry

    route_config = RouteConfig(
        agent_list=["test-agent"],
        platforms={
            "mock": PlatformConfig(
                default_agent="test-agent",
                conversation_routes={
                    "c1": ConversationRoute(agent="test-agent", model="gpt-4.1"),
                },
            ),
        },
    )

    class TestAgent:
        @property
        def name(self) -> str:
            return "test-agent"

        async def handle(
            self, message: Message, session_id: str,
            model: str | None = None, workdir: str | None = None,
        ) -> Response:
            return Response(text=f"echo: {message.text}")

    agent_registry.clear()
    register_agent(TestAgent())

    processor = MessageProcessor(route_config, "", agent_registry, timeout_s=20.0)
    app.state.processor = processor

    return app


@pytest.mark.asyncio
async def test_webhook_mock_valid(mock_app):
    async with AsyncClient(
        transport=ASGITransport(app=mock_app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/webhook/mock",
            content=json.dumps({"text": "hello", "userId": "u1", "conversationId": "c1"}),
            headers={"content-type": "application/json"},
        )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_webhook_unknown_platform(mock_app):
    async with AsyncClient(
        transport=ASGITransport(app=mock_app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/webhook/unknown",
            content=b"{}",
        )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_webhook_command_handled(mock_app):
    """Slash command should be handled without reaching the agent."""
    async with AsyncClient(
        transport=ASGITransport(app=mock_app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/webhook/mock",
            content=json.dumps({"text": "/agent", "userId": "u1", "conversationId": "c1"}),
            headers={"content-type": "application/json"},
        )
    assert resp.status_code == 200
```

**Step 5: Remove any lingering imports of deleted modules**

Check `src/chatpilot/server/__init__.py` and `src/chatpilot/server/webhook.py` for any remaining imports of `dispatcher`, `model_command`, old types.

Also clean `src/chatpilot/dispatch/route_loader.py` — remove old `load_routes`, `save_routes` functions and the old `RouteMap` import if no longer needed.

**Step 6: Run all tests**

Run: `uv run pytest -v`
Expected: All tests PASS

**Step 7: Lint**

Run: `uv run ruff check src/ tests/`
Expected: Clean

**Step 8: Commit**

```bash
git add -A
git commit -m "refactor: remove old dispatcher, keyword types, and /倉管 handler"
```

---

### Task 8: Final verification — full test suite + lint

**Step 1: Run full test suite**

Run: `uv run pytest -v`
Expected: All tests PASS (route_config, command_handler, processor, pending_queue, webhook, adapter contract)

**Step 2: Lint**

Run: `uv run ruff check src/ tests/`
Expected: Clean

**Step 3: Start server and verify**

Run: `uv run uvicorn chatpilot.server:app --host 0.0.0.0 --port 2999 --reload`
Expected: Server starts, loads new routes.yaml format, shows "2 platform(s)" or similar

**Step 4: Commit any final fixes**

```bash
git add -A
git commit -m "chore: final cleanup and verification"
```
