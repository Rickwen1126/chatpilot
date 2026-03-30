---
name: speckit.specify
description: Create or update the feature specification from a natural language feature description.
---

Use this repo-local skill when the user asks for `speckit.specify` or the equivalent Claude command.

1. Read `../../../.claude/commands/speckit.specify.md`.
2. Follow the spec-generation flow there, including branch-numbering and `.specify` script usage.
3. When the command mentions Claude-specific follow-ups, convert them into Codex next-step recommendations.
4. Keep the resulting spec grounded in the user's feature description and current repo context.
