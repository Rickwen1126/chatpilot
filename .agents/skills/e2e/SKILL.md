---
name: e2e
description: Run layered chatpilot E2E verification with data-level proof. Default path uses the self-contained runner; localhost:2999 and Android real-device LINE smoke are higher-fidelity secondary modes.
---

Use this repo-local skill when the user asks for `e2e`, `/e2e`, "跑 E2E", or "E2E 測試".

1. Read `../../../.claude/commands/e2e.md`.
2. Follow that workflow, but adapt command-oriented wording to Codex tools and current repo state.
3. Enforce the E2E standard in `../../../AGENTS.md`: prove correctness with data-level verification, not just process status.
4. Prefer the self-contained runner first. Only require a live server when the user explicitly asks to validate localhost:2999 behavior.
5. When validating a running server, verify the actual runtime behavior on `localhost:2999`, not just script output.
6. When Android + real LINE is available, use it for high-value smoke scenarios and require both:
   - user-visible proof in LINE UI
   - server-side proof in logs / DB / `files.db`
7. Treat real-device smoke as a realistic audit layer, not the main coverage source.
