---
name: speckit.tasks
description: Generate an actionable, dependency-ordered tasks.md for the feature based on available design artifacts.
---

Use this repo-local skill when the user asks for `speckit.tasks` or the equivalent Claude command.

1. Read `../../../.claude/commands/speckit.tasks.md`.
2. Follow the task-generation workflow there and preserve its task formatting constraints.
3. Keep task grouping aligned with user stories and independent testability.
4. Translate Claude handoffs into Codex next-step recommendations only after task generation is complete.
