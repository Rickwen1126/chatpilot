# Architecture Refactor: Clean Pipeline + `/agent` Command

## Context

The MVP (`001-agent-gateway-mvp`) works end-to-end but has architectural issues discovered during testing:

- `/倉管` is hardcoded in webhook.py, bypassing the dispatcher
- webhook.py mixes transport (HTTP), business logic (gate, dispatch, pending), and platform concerns (LINE reply tokens)
- routes.yaml stores keyword-based routing which is inflexible — no way to switch agents dynamically
- The gate is keyed by session_id only, not considering agent changes mid-conversation

This refactor separates concerns into a clean pipeline: **Transport → Adapter → Processor → Adapter**, adds an `/agent` command for explicit agent switching, and restructures routes.yaml to be conversation-centric.

## Design

### 1. New `routes.yaml` Schema

```yaml
agentList:
  - general-agent
  - warehouse-agent

platforms:
  line:
    defaultAgent: general-agent
    conversationRoutes:
      "null":                          # private chats (conversation_id is None)
        agent: general-agent
        model: claude-haiku-4.5
        workdir: ~/code/chatpilot/
      # Group chats use conversation_id as key:
      # "C1234567890abcdef":
      #   agent: warehouse-agent
      #   model: claude-haiku-4.5
      #   workdir: ~/warehouse-data/
  mock:
    defaultAgent: general-agent
    conversationRoutes:
      "null":
        agent: general-agent
        model: gpt-4.1
        workdir: ~/code/chatpilot/
```

**Pydantic types** (in `core/types.py`):

```python
class ConversationRoute(BaseModel):
    agent: str
    model: str | None = None
    workdir: str | None = None

class PlatformConfig(BaseModel):
    default_agent: str = Field(alias="defaultAgent")
    conversation_routes: dict[str, ConversationRoute] = Field(
        default_factory=dict, alias="conversationRoutes"
    )

class RouteConfig(BaseModel):
    agent_list: list[str] = Field(alias="agentList")
    platforms: dict[str, PlatformConfig]
```

**Rules:**
- `agentList` validated against `AgentRegistry` at startup
- `defaultAgent` used when conversation has no explicit route in `conversationRoutes`
- `"null"` key = private chats
- `/agent` and `/model` commands persist changes to yaml via hot-reload-safe write

### 2. MessageProcessor

**File:** `src/chatpilot/processing/processor.py`

Owns all business logic. Platform-agnostic.

```python
class MessageProcessor:
    async def process(self, msg: Message, adapter: ChannelAdapter) -> None:
        session_id = SessionManager.get_session_id(...)

        # 1. Commands — instant, no gate
        reply = self.command_handler.try_handle(msg, ...)
        if reply:
            await adapter.send_response(msg, Response(text=reply))
            return

        # 2. Gate check
        if session_gate.is_busy(session_id):
            session_gate.queue(session_id, msg.text)
            await adapter.send_response(msg, Response(text="目前正在處理中，請稍候…"))
            return

        session_gate.acquire(session_id)
        try:
            # 3. Resolve agent from route config
            agent_name, model, workdir = self._resolve_route(msg)
            agent = get_agent(agent_name)

            # 4. Collect pending messages
            pending_texts = self._collect_pending(session_id)

            # 5. Agent handle with timeout
            response = await asyncio.wait_for(
                agent.handle(msg, session_id, model=model, workdir=workdir),
                timeout=self.timeout_s
            )

            # 6. Combine pending + response, send
            reply_text = self._combine_pending(pending_texts, response.text)
            await adapter.send_response(msg, Response(text=reply_text))
            bg = False
        except asyncio.TimeoutError:
            for text in pending_texts:
                pending_queue.enqueue(session_id, text)
            await adapter.send_processing_ack(msg)
            asyncio.create_task(self._background_handle(...))
            bg = True
        finally:
            if not bg:
                self._release_gate(session_id)
```

### 3. CommandHandler

**File:** `src/chatpilot/processing/command_handler.py`

All slash commands handled here. Instant, bypass gate.

```python
class CommandHandler:
    def try_handle(self, msg, route_config, routes_path) -> str | None:
        text = msg.text.strip()
        if text.startswith("/model"):
            return self._handle_model(text, msg, route_config, routes_path)
        if text.startswith("/agent"):
            return self._handle_agent(text, msg, route_config, routes_path)
        return None
```

**`/agent` command:**
- `/agent` → list available agents (from `agentList`) + show current for this conversation
- `/agent <name>` → fuzzy match against `agentList`, update `conversationRoutes`, persist to yaml
- If agent is busy processing, switch happens immediately; in-flight task finishes in background and result is still delivered via pending queue

### 4. Thin webhook.py

```python
@router.post("/webhook/{platform}")
async def webhook_handler(platform: str, request: Request) -> Response:
    adapter = app.state.adapter_registry.get(platform)
    if not adapter:
        return Response(status_code=400)
    raw_body = await request.body()
    signature = request.headers.get("x-line-signature", "")
    if not adapter.verify_signature(raw_body, signature):
        return Response(status_code=401)
    messages = adapter.parse_messages_with_signature(raw_body, signature)
    for msg in messages:
        await app.state.processor.process(msg, adapter)
    return Response(status_code=200)
```

### 5. BaseAgent Protocol Change

```python
class BaseAgent(Protocol):
    @property
    def name(self) -> str: ...

    async def handle(
        self, message: Message, session_id: str,
        model: str | None = None, workdir: str | None = None
    ) -> Response: ...
```

`workdir` added so agents can operate in a specified directory context. Agents that don't need it ignore it.

### 6. Dispatcher Simplification

The `dispatch/dispatcher.py` (3-phase keyword matching) is **deleted**. Routing becomes a simple dict lookup in `MessageProcessor._resolve_route()`:

```python
def _resolve_route(self, msg: Message) -> tuple[str, str | None, str | None]:
    platform_config = self.route_config.platforms.get(msg.platform)
    if not platform_config:
        return default_agent, None, None
    key = msg.conversation_id or "null"
    route = platform_config.conversation_routes.get(key)
    if not route:
        return platform_config.default_agent, None, None
    return route.agent, route.model, route.workdir
```

## File Changes

### New Files
- `src/chatpilot/processing/__init__.py`
- `src/chatpilot/processing/processor.py`
- `src/chatpilot/processing/command_handler.py`

### Modified Files
- `src/chatpilot/core/types.py` — add `ConversationRoute`, `PlatformConfig`, `RouteConfig`; remove `KeywordMapping`, `KeywordMatch`, `FallbackMatch`, `Ignored`, `RouteRule`, `RouteMap`
- `src/chatpilot/agents/base.py` — add `workdir` param to `handle()`
- `src/chatpilot/agents/general/__init__.py` — accept `workdir` param
- `src/chatpilot/agents/warehouse/__init__.py` — accept `workdir` param
- `src/chatpilot/dispatch/route_loader.py` — parse new yaml schema (`RouteConfig`)
- `src/chatpilot/server/__init__.py` — wire `MessageProcessor`, pass `RouteConfig`
- `src/chatpilot/server/webhook.py` — thin down to ~20 lines
- `config/routes.yaml` — new format

### Deleted Files
- `src/chatpilot/dispatch/dispatcher.py`
- `src/chatpilot/commands/model_command.py` (logic moves to `CommandHandler`)

### Test Updates
- Remove dispatcher tests (keyword matching)
- Add `MessageProcessor` tests
- Add `CommandHandler` tests (`/agent`, `/model`)
- Add `RouteConfig` schema tests
- Update webhook integration tests

## Verification

1. **Unit tests:** `uv run pytest` — all new + updated tests pass
2. **Lint:** `uv run ruff check src/`
3. **E2E test flow:**
   - Start server: `uv run uvicorn chatpilot.server:app --port 2999`
   - Send message via LINE → routed to `general-agent` (default)
   - Send `/agent` → shows available agents + current
   - Send `/agent warehouse` → switches, persists to yaml
   - Send inventory query → routed to `warehouse-agent`
   - Send `/agent general` → switches back
   - Send `/model sonnet` → model changes, persists
   - Verify yaml file updated correctly after each command
