---
name: e2e
description: Run chatpilot E2E tests with data-level verification. Default path uses the self-contained runner; localhost:2999 is only for explicit live-server validation.
---

Use this repo-local skill when the user asks for `e2e`, `/e2e`, "跑 E2E", or "E2E 測試".

1. Read `../../../.claude/commands/e2e.md`.
2. Follow that workflow, but adapt command-oriented wording to Codex tools and current repo state.
3. Enforce the E2E standard in `../../../AGENTS.md`: prove correctness with data-level verification, not just process status.
4. Prefer the self-contained runner first. Only require a live server when the user explicitly asks to validate localhost:2999 behavior.
