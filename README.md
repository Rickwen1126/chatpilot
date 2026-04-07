# ChatPilot

Multi-platform AI chatbot gateway. Routes messages from LINE (and other channels) to configurable chatbots backed by GitHub Copilot SDK, with tools, async pipelines, observer mode, and cron scheduling.

## Quick Start

```bash
# Install
uv sync

# Configure
cp .env.example .env   # Fill in LINE_CHANNEL_SECRET, LINE_CHANNEL_ACCESS_TOKEN, etc.
vim config/route_settings.yaml  # Define chatbots, discovery rules, shared config
vim config/route_bindings.yaml  # Define exact route bindings + fallback bindings

# Run
uv run uvicorn chatpilot.server:create_app --factory --port 2999

# Test
uv run chatpilot-cli chat "hello"
```

## Architecture

```
LINE / Mock / CLI
      │
      ▼
  Webhook ──► Hub ──► BindingRouter ──► ChatbotManager ──► Copilot SDK
               │           │                   │
               │      score-based          per-route
               │      routing              session pool
               │
               ├── Context Buffer (sliding window, group chat prefix)
               ├── Observer Mode (silent collect → batch LLM → DB)
               └── Commands (/chatbot, /model)
                                               │
                                          ToolFactory
                                          (access control)
                                               │
                              ┌────────────────┼────────────────┐
                         Builtin Tools    Async Pipelines    CronScheduler
                         (25 tools)       (general-agent,    (reminders,
                                           browser, vision)   schedules)
```

## Project Structure

```
src/chatpilot/
  adapters/          # LINE, Mock, CLI — ChannelAdapter Protocol
  chatbot/           # ChatbotManager + ChatbotSession (per-route SDK pool)
  cli/               # chatpilot-cli entry point
  core/              # types, config, time_service, errors
  cron/              # CronScheduler + cron expression parser
  hub/               # MessageHub, ContextBuffer, mention filter
  memory/            # SqliteMemoryStore (memos, reminders, schedules, observations)
  pipeline/          # PipelineExecutor + sample nodes
  routing/           # BindingRouter (score-based routing)
  scheduler/         # TaskScheduler + RunnerPool (async task queue)
  sdk/               # SdkClient wrapper for Copilot SDK
  server/            # FastAPI app factory, webhook handlers, admin API
  storage/           # R2 media upload
  tools/builtin/     # 25 builtin tools
config/
  route_settings.yaml # Chatbots, discovery rules, shared route settings
  route_bindings.yaml # Single source of truth for all bindings
tests/
  unit/              # pytest
  e2e/               # Bash-based E2E (run_e2e.sh)
```

## Configuration

`config/route_settings.yaml` defines non-binding settings, while
`config/route_bindings.yaml` is the single source of truth for bindings:

```yaml
# config/route_settings.yaml
timezone: "Asia/Taipei"            # System display timezone

trigger_keywords: ["bot"]          # Group keyword triggers

match_weights:                     # Binding score weights
  group_id: 10
  user_id: 8
  platform: 5

chatbots:
  buddy:
    model: gpt-5.4-mini
    system_message: "..."
    tools: [get_calendar, web_search, save_memo, ...]
    context_window: 50
    timeout: 300

scheduler:
  concurrent_runners: 2
  task_timeout: 300

cron_scheduler:
  tick_interval: 60
  available_tools: [general-agent, browser-search]
```

```yaml
# config/route_bindings.yaml
route_bindings:
  line:demo:Cxxx:
    match:
      platform: line:demo
      group_id: Cxxx
    chatbot: my-assistant
    reply_policy: addressed
    processing_policy: interactive
    source: manual

fallback_bindings:
  - match: { platform: line:demo }
    chatbot: buddy
  - chatbot: buddy
```

## Key Features

### Routing & Bindings

Messages are scored against bindings by match dimensions (group_id, user_id, platform). Highest score wins. Per-route chatbot and model overrides via `/chatbot` and `/model` commands.

### Context Buffer

Group chat messages are buffered in a sliding window. When the bot is mentioned, the buffer is drained and prepended as context:

```
[群組近期對話]
[背景] UserA: 今天要出貨
[背景] UserB: 收到
---
[以下是直接對你說的訊息]
```

### Observer VNext

Observer vNext is configured per-binding, not per-chatbot.

```yaml
# config/route_settings.yaml
route_groups:
  ops:
    description: Shared operational knowledge

observation_profiles:
  ops_batch:
    mode: batch
    batch_size: 10
    instructions: |
      Summarize reusable background knowledge from this route.

# config/route_bindings.yaml
route_bindings:
  line:demo:Cxxx:
    match:
      platform: line:demo
      group_id: Cxxx...
    chatbot: my-observer
    reply_policy: never
    processing_policy: none
    observation:
      capture:
        group: ops
        profile: ops_batch

  line:demo:Uxxx:
    match:
      platform: line:demo
      user_id: Uxxx...
    chatbot: my-admin
    reply_policy: addressed
    processing_policy: interactive
    observation:
      consume: [ops]

fallback_bindings:
  - match: { platform: line:demo }
    chatbot: buddy
  - chatbot: buddy
```

Capture remains route-local in SQLite. `query_observations(group=...)` expands an observation group into source routes at query time, with consumer-route permission checks.

### TimeService

Singleton for all time operations. No module should `import datetime` to calculate time directly.

- **Internal:** always UTC (DB storage, diff calculations)
- **Display:** always config timezone (tool results, system prompts)
- **System prompt injection:** chatbot automatically knows current date/time and timezone
- **LINE timestamps:** `event.timestamp` (epoch ms) stored as UTC; `received_at` tracked separately for reply token TTL

### Cron Scheduler

Scans SQLite every 60s for due items:

- **Reminders:** one-time, enqueues general-agent task at `due_at`
- **Schedules:** recurring cron expressions (`daily 08:00`, `weekly mon 09:00`, `interval 30m`), resets `next_run_at` after each trigger

### Async Pipelines

Long-running tasks execute in background via RunnerPool:

| Pipeline | Purpose |
|----------|---------|
| `general-agent` | SDK session with tools for arbitrary tasks |
| `browser-search` | Playwright web browsing + screenshot |
| `batch-image-vision` | Batch image analysis via vision API |
| `echo` | Debug echo |

Chatbot triggers pipelines via `submit_task` / `browse_task` / `batch_image_analyze` tools. Results push back to conversation when complete.

### Tool Access Control

```
GLOBAL            — chatbot + pipeline can use
CHATBOT_ONLY      — chatbot only
AGENT_TEAM_ONLY   — pipeline only
AGENT_TEAM_TRIGGER — chatbot can call to enqueue async task; pipeline cannot (recursion guard)
```

## Builtin Tools

| Tool | Description |
|------|-------------|
| `get_calendar` | Current date/time + weekly calendar (config timezone) |
| `web_search` | Web search (SearXNG / Brave) |
| `download_media` | Fetch image/file from platform |
| `show_image` | Push image back to user via R2 |
| `browser_navigate/eval/tabs` | Chrome CDP browser automation |
| `warehouse` | Inventory CRUD (search, get_items, replace_layer, lock/unlock) |
| `quote_search` | Quote lookup with filters |
| `document_edit` | Edit DOCX/XLSX documents |
| `batch_image_analyze` | Submit batch vision analysis (async) |
| `submit_task` | Enqueue arbitrary async task |
| `browse_task` | Enqueue browser search task |
| `query_observations` | Query group-based observer knowledge (permission-gated) |
| `save_memo` / `list_memos` / `delete_memo` | Per-route memo CRUD |
| `save_custom_prompt` / `list_custom_prompts` / `delete_custom_prompt` | Persistent prompt customization |
| `add_reminder` | Schedule one-time reminder |
| `schedule_task_cron` / `list_schedules` / `cancel_schedule` | Recurring cron task management |
| `task_history` | View async task history |

## Adapters

| Adapter | Notes |
|---------|-------|
| **LINE** | Webhook signature verification, reply token TTL (25s fallback to push), 5000 chars/msg split, `format_hint` disables Markdown, image/file ref parsing |
| **Mock** | In-memory test adapter, captures replies |
| **CLI** | `chatpilot-cli` bridge for local testing |

New adapters implement `ChannelAdapter` Protocol: `verify_request`, `parse_messages`, `send_reply`, `push_message`, `download_media`, `format_hint`.

## Admin API

```bash
GET  /health                  # Status + version + uptime
GET  /cli/routes              # Known routes + bindings + labels + known chatbots
POST /cli/routes/label        # Set/remove route label
POST /cli/routes/sync         # Sync labels from LINE API
POST /cli/reload              # Hot-reload config
POST /webhook/{platform}      # Inbound webhook
POST /cli/chat                # Synchronous test endpoint
```

## CLI

```bash
chatpilot-cli chat "你好"                    # Send message
chatpilot-cli chat "你好" --user "Uxxx"      # As specific user
chatpilot-cli --url http://host:2999 chat "hi"  # Custom server
```

## Storage

| Layer | Backend | Data |
|-------|---------|------|
| In-memory | Python dicts | Hub state, context buffer, session pool |
| SQLite (WAL) | `data/chatpilot.db` | Memos, reminders, schedules, observations |
| SQLite (WAL) | `data/tasks.db` | Async task history |
| Disk JSON | `data/route_labels.json` | Route display labels |
| Cloudflare R2 | S3-compatible | Uploaded images and files |

## Development

```bash
# Lint + test
uv run ruff check src/ && uv run pytest tests/

# E2E (requires running server on :2999)
bash tests/e2e/run_e2e.sh

# Single test
uv run pytest tests/unit/test_time_service.py -v
```

**Dev cycle:** implement → ruff + pytest → E2E (24 tests) → verify logs → commit.

## Environment Variables

```
LINE_CHANNEL_SECRET          # LINE webhook signature verification
LINE_CHANNEL_ACCESS_TOKEN    # LINE Messaging API
PORT                         # Server port (default 2999)
ROUTE_SETTINGS_PATH          # Route settings file path (default config/route_settings.yaml)
ROUTE_BINDINGS_PATH          # Route bindings file path (default config/route_bindings.yaml)
ROUTES_PATH                  # Legacy alias for ROUTE_SETTINGS_PATH
R2_ACCESS_KEY_ID             # Cloudflare R2
R2_SECRET_ACCESS_KEY
R2_ENDPOINT
R2_BUCKET
R2_PUBLIC_URL
```

## Tech Stack

- **Python 3.11+**, FastAPI, Pydantic v2, uvicorn
- **GitHub Copilot SDK** — LLM session management
- **line-bot-sdk v3** — LINE Messaging API
- **aiosqlite** — async SQLite with WAL mode
- **Playwright** — browser automation pipeline
- **watchdog** — config hot-reload
- **ruff** — linting and formatting
