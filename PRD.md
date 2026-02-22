# Chatpilot — Personal AI Agent Gateway

## Overview

Chatpilot is a channel-agnostic personal AI agent gateway. It receives messages from multiple chat platforms (LINE, Telegram, Web, etc.), routes them through a dispatcher, and delegates to specialized agents that call downstream services.

## Problem

- Multiple chat platforms, each with their own API format
- Multiple downstream services (warehouse management, reports, calendar, etc.)
- Need a single personal AI entry point that can grow with new channels and services
- Don't want to rebuild agent logic for each platform

## Architecture

```
Channels (Adapters)        Agent Core              Services (Downstream)
├── LINE adapter                                   ├── Warehouse API
├── Telegram (future)  →   Dispatcher  →           ├── Report service
├── Web chat (future)      └── Agents              ├── Calendar (future)
├── Voice (future)           ├── warehouse_agent   └── ...
└── ...                      ├── report_agent
                             └── ...
```

### Core Principles

1. **Channel-agnostic core** — Agents never see platform-specific data. Channel adapters translate to/from a unified `Message` format.
2. **Fast path / slow path dispatch** — Group ID match (O(1) dict lookup) first, keyword match second, AI dispatch only as last resort. Minimize token cost.
3. **Ports & Adapters (Hexagonal)** — Core logic has zero dependencies on external platforms. Channels and services are pluggable adapters.
4. **Independent lifecycle** — Chatpilot deploys independently from any downstream service. Warehouse API changes don't break Chatpilot, and vice versa.

### Unified Message Format

```python
class Message:
    text: str
    user_id: str
    channel: str          # "line" | "telegram" | "web"
    group_id: str | None  # platform group/room identifier
    context: dict         # reply_token, platform-specific metadata

class Response:
    text: str
    attachments: list     # images, files, etc. (future)
```

### Dispatcher (Route Map)

```python
# Layer 1: Group ID → agent (fastest)
GROUP_ROUTES = {
    "Cxxxx1": "warehouse",   # 倉庫工作群
    "Cxxxx2": "warehouse",   # 老闆群
}

# Layer 2: Keyword → agent (fast)
KEYWORD_ROUTES = {
    "庫存": "warehouse",
    "物料": "warehouse",
    "週報": "report",
}

# Layer 3: Default handler (no AI cost if unmatched)
DEFAULT = "ignore"  # or "echo" for testing
```

## Tech Stack

- **Runtime**: Python 3.12+
- **Agent SDK**: GitHub Copilot SDK (`github-copilot-sdk`) — handles planning, tool calling, multi-turn
- **Model**: GPT-4.1 (via GitHub Copilot free tier)
- **Web framework**: FastAPI (webhook endpoints)
- **Deployment**: Self-hosted (cloudflared tunnel for HTTPS)

## Phase 1: MVP — LINE + Warehouse Query

### Goal
LINE 群組可查倉庫物料庫存，自然語言問答。

### Scope
- [ ] **LINE channel adapter** — Webhook receive + reply, signature verification
- [ ] **Dispatcher** — Group ID + keyword routing
- [ ] **Warehouse agent** — Copilot SDK agent with tools:
  - `search_materials(query)` — 物料搜尋
  - `check_inventory(unit_id, layer)` — 查特定位置庫存
  - `find_location(material_name)` — 查物料在哪裡
- [ ] **Warehouse service connector** — HTTP client calling warehouse API (`warehouse.shinyipaint.com.tw`)
- [ ] **Config** — LINE tokens, route map, API endpoints (.env)

### User Stories

1. 工人在 LINE 群組打「虹牌450在哪」→ agent 回覆「A2 第2層、B3 第1層，共 12 罐」
2. 老闆在群組打「庫存快沒的有哪些」→ agent 回覆庫存不足清單
3. 不相關的群組聊天 → 不回應（keyword 沒 match）

### Non-Goals (Phase 1)
- No Telegram/Web adapters yet
- No weekly report agent yet
- No image/voice input yet
- No conversation memory across sessions

## Phase 2: Report + Multi-channel (Future)

- [ ] Weekly report agent — 自動產生 + 發送倉庫週報
- [ ] Conversation memory — 跨 session 記憶
- [ ] Telegram adapter
- [ ] Web chat adapter
- [ ] Image input support (拍照查物料)

## Project Structure

```
chatpilot/
├── PRD.md
├── CLAUDE.md
├── pyproject.toml
├── .env.example
├── src/
│   ├── main.py              # FastAPI app entry
│   ├── config.py            # Settings, route map
│   ├── models.py            # Message, Response unified types
│   ├── dispatcher.py        # Route map + dispatch logic
│   ├── channels/
│   │   ├── base.py          # ChannelAdapter interface
│   │   └── line.py          # LINE webhook + reply
│   ├── agents/
│   │   ├── base.py          # BaseAgent interface
│   │   └── warehouse.py     # Warehouse query agent
│   └── services/
│       └── warehouse.py     # HTTP client for warehouse API
└── tests/
    ├── test_dispatcher.py
    └── test_warehouse_agent.py
```

## Setup Requirements

- LINE Official Account with Messaging API channel
- Channel Secret + Channel Access Token
- GitHub Copilot subscription (free tier OK)
- Python 3.12+
- cloudflared tunnel (reuse existing setup)

## Success Criteria

Phase 1 is done when:
1. Send "虹牌450在哪" in LINE group → get correct inventory location reply
2. Send "查庫存 A2" → get A2 shelf inventory summary
3. Unrelated messages in routed groups → no response
4. Messages from unrouted groups → no response
