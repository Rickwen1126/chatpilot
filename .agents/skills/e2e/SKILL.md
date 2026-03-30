---
name: e2e
description: Run chatpilot E2E tests against localhost:2999. Repo-local wrapper for .claude/commands/e2e.md.
---

Use this repo-local skill when the user asks for `e2e`, `/e2e`, "跑 E2E", or "E2E 測試".

1. Read `../../../.claude/commands/e2e.md`.
2. Follow that workflow, but adapt command-oriented wording to Codex tools and current repo state.
3. Enforce the E2E standard in `../../../AGENTS.md`: prove correctness with data-level verification, not just process status.
4. If the server is not running or prerequisites are missing, state the blocker clearly before proceeding.
