---
name: speckit.plan
description: Execute the implementation planning workflow using the plan template to generate design artifacts.
---

Use this repo-local skill when the user asks for `speckit.plan` or the equivalent Claude command.

1. Read `../../../.claude/commands/speckit.plan.md`.
2. Follow that planning workflow and use the repo's `.specify` scripts as the source of truth.
3. Convert Claude handoffs into Codex next-step recommendations or subagent usage only when needed.
4. Stop after the planning artifacts are generated, unless the user explicitly asks for the next phase.
