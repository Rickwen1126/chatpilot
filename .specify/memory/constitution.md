<!--
Sync Impact Report
===================
- Version change: 1.0.0 → 1.1.0 (MINOR — new principle added)
- Modified principles: none
- Added principles:
  - VI. Documentation Language (繁體中文)
- Added sections: none
- Removed sections: none
- Templates requiring updates:
  - .specify/templates/plan-template.md — ✅ no update needed
    (Constitution Check section already references constitution file;
     language rule enforced at authoring time, not in template)
  - .specify/templates/spec-template.md — ✅ no update needed
    (template is structural; language rule enforced at authoring time)
  - .specify/templates/tasks-template.md — ✅ no update needed
    (template is structural; language rule enforced at authoring time)
  - .specify/templates/checklist-template.md — ✅ no update needed
- Follow-up TODOs: none
-->

# Chatpilot Constitution

## Core Principles

### I. Three-Layer Architecture

Every feature MUST respect the three-layer boundary:

1. **Chat Channel** — Platform adapters (LINE, Telegram, Web, etc.)
   that translate platform-specific protocols into the unified
   `Message`/`Response` format. No business logic lives here.
2. **Copilot SDK** — Agent core powered by GitHub Copilot SDK.
   Dispatcher routes messages; agents plan, call tools, and
   produce responses. This layer owns all AI/business logic.
3. **Copilot CLI** — Local command-line interface that invokes
   the same Copilot SDK agents without a chat channel, enabling
   development, testing, and scripting without deploying webhooks.

Cross-layer imports MUST flow inward only:
`Channel → SDK ← CLI`. The SDK layer MUST NOT import from
Channel or CLI. Violations indicate an architectural breach.

### II. Channel-Agnostic Core

Agents MUST NOT access platform-specific data. All channel
adapters MUST translate inbound webhooks into the unified
`Message` type and outbound `Response` back into platform
calls. Adding a new channel MUST NOT require changes to any
agent or dispatcher code.

### III. Fast-Path Dispatch

Message routing MUST follow a three-tier cost hierarchy:

1. **Group ID lookup** — O(1) dict match (zero token cost)
2. **Keyword match** — string scan (zero token cost)
3. **AI dispatch** — LLM classification (last resort only)

Unmatched messages MUST be silently ignored (no AI fallback
unless explicitly configured). Minimizing token cost is a
first-class design constraint.

### IV. Ports & Adapters (Hexagonal)

Core logic MUST have zero direct dependencies on external
platforms or downstream services. Channels and services are
pluggable adapters behind abstract interfaces:

- `ChannelAdapter` for inbound/outbound chat platforms
- `BaseAgent` for agent implementations
- Service connectors (HTTP clients) for downstream APIs

All adapters MUST be independently replaceable without
modifying core dispatcher or agent code.

### V. Independent Lifecycle

Each layer and each downstream service MUST deploy
independently. Specifically:

- Warehouse API changes MUST NOT break Chatpilot.
- Chatpilot changes MUST NOT require downstream redeployment.
- Channel adapters MUST be addable/removable without touching
  the agent core.

Version contracts between layers are enforced through the
unified `Message`/`Response` types and tool interfaces, not
through shared code or tight coupling.

### VI. Documentation Language

所有由 speckit 產出的設計文件 MUST 以**繁體中文**撰寫，
包含但不限於：

- `spec.md`（功能規格）
- `plan.md`（實作計畫）
- `tasks.md`（任務清單）

技術專有名詞（類別名、函式名、套件名、CLI 指令等）維持
英文原文，不需翻譯。程式碼區塊與檔案路徑維持英文。

此規則確保非工程背景的利害關係人能直接閱讀設計文件，
降低溝通成本。

## Technology Constraints

| Constraint | Value |
|---|---|
| Runtime | Python 3.12+ |
| Agent SDK | GitHub Copilot SDK (`github-copilot-sdk`) |
| Model | GPT-4.1 via GitHub Copilot free tier |
| Web framework | FastAPI (webhook endpoints) |
| Deployment | Self-hosted with cloudflared tunnel |
| Config | `.env` for secrets; Python modules for route maps |

- All new dependencies MUST be justified against the existing
  stack. Prefer stdlib + existing deps over new packages.
- Async-first: FastAPI endpoints and HTTP clients MUST use
  `async`/`await`. Blocking I/O in the event loop is forbidden.

## Development Workflow

- **Unified Message contract** — Any change to `Message` or
  `Response` types MUST be reviewed for backward compatibility
  across all three layers before merge.
- **Adapter isolation** — Channel adapter PRs MUST NOT touch
  files outside `src/channels/`. Agent PRs MUST NOT touch
  files outside `src/agents/` and `src/services/`.
- **Route map changes** — Adding or removing dispatcher routes
  MUST be documented in the PR description with rationale.
- **Testing** — Each layer MUST be testable in isolation:
  - Channels: mock the dispatcher
  - Agents: mock service connectors
  - CLI: invoke agents directly without HTTP
- **Secrets** — `.env` files MUST NOT be committed. Use
  `.env.example` as the canonical reference for required
  environment variables.

## Governance

This constitution is the highest-authority document for
Chatpilot development decisions. When a PR or design conflicts
with a principle above, the constitution wins unless formally
amended first.

**Amendment procedure**:
1. Propose the change with rationale in a PR modifying this file.
2. Document the migration impact on existing code.
3. Update the version following semver rules below.

**Versioning policy** (semantic versioning):
- **MAJOR**: Principle removed, redefined, or made incompatible
  with prior interpretation.
- **MINOR**: New principle or section added, or existing
  guidance materially expanded.
- **PATCH**: Clarifications, wording fixes, non-semantic
  refinements.

**Compliance**: All PRs MUST be checked against the principles
in this constitution. The plan template's "Constitution Check"
gate references this document.

**Version**: 1.1.0 | **Ratified**: 2026-02-22 | **Last Amended**: 2026-02-22
