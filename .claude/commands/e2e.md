---
description: Run chatpilot E2E tests against localhost:2999. Triggers on /e2e, "跑 E2E", "E2E 測試".
---

## E2E Test Runner

Run all E2E tests against a running chatpilot server.

### Prerequisites

Server must be running. Check with:
```bash
curl -s http://localhost:2999/health
```

If not running, start it:
```bash
uv run uvicorn chatpilot.server:create_app --factory --host 0.0.0.0 --port 2999
```

### Execution

Run the E2E test script:
```bash
bash tests/e2e/run_e2e.sh
```

### Test Coverage

| Test | Verifies |
|------|----------|
| Health | Server responds, version correct |
| CLI Chat | Full pipeline: hub → router → chatbot → SDK → response |
| /chatbot list | Command routing + chatbot registry |
| Mock Webhook | Adapter parse + hub receive |
| Unknown Platform | 404 for unregistered adapter |
| Trigger Keywords | "bot 你好" triggers without @mention in group |
| Memo | save_memo → confirm → list_memos (Memory Store CRUD) |
| Reminder | add_reminder + CronScheduler tick push |
| Schedule + Cancel | schedule_task_cron + list_schedules + cancel by index |
| Config Reload | /cli/reload endpoint |
| Context Buffer | Group non-mention → buffer → @mention drains context |

### After Running

- Report pass/fail count
- If failures: check server logs for details
- Reminder test needs ~60s for CronScheduler tick
