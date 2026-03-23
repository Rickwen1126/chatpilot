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

### E2E Checklist

Each item maps to a test scenario. All must pass before release.

**Core Gateway**
- [ ] Health endpoint returns 200 + version
- [ ] CLI chat full pipeline (hub → router → chatbot → SDK → response)
- [ ] Mock webhook 200 OK
- [ ] Unknown platform returns 404
- [ ] /chatbot list shows all chatbots
- [ ] /chatbot {name} switches chatbot

**Group Behavior**
- [ ] Group non-mention → silent buffer (no response)
- [ ] Group @bot mention → chatbot responds with context prefix
- [ ] Group "bot 你好" keyword trigger → chatbot responds (trigger_keywords)
- [ ] Group @Bot /chatbot list → slash command works
- [ ] Busy gate: second mention while processing → "處理中" reply

**Adapters**
- [ ] LINE private chat → chatbot responds
- [ ] LINE group @bot → chatbot responds
- [ ] LINE reply token expired → fallback to push
- [ ] LINE image → [圖片 ref:line:{id}] in context buffer
- [ ] LINE @bot "剛那張圖是什麼" → LLM calls download_media

**Memory Store**
- [ ] save_memo → LLM asks confirmation → stores in SQLite
- [ ] list_memos → shows saved memos
- [ ] delete_memo → removes memo
- [ ] save_custom_prompt → stores preference + marks needs_rebuild
- [ ] Session rebuild after custom_prompt → new system_message includes preference

**Reminder + Schedule**
- [ ] add_reminder → stored with due_at
- [ ] CronScheduler tick → due reminder pushed
- [ ] schedule_task_cron → stored with next_run_at
- [ ] CronScheduler tick → due schedule triggers pipeline
- [ ] list_schedules → shows pending reminders + schedules
- [ ] cancel_schedule by index → deletes correct item

**Session**
- [ ] Server restart → resume_session preserves conversation history
- [ ] Broken session (timeout) → next message creates new session
- [ ] Config hot reload → routes.yaml change takes effect without restart

**Shinyipaint Tools**
- [ ] quote_search → 切 shinyipaint chatbot，查詢虹牌報價，回傳歷史資料
- [ ] document_edit xlsx round-trip → 建立 xlsx → append rows → 驗證內容
- [ ] document_edit docx round-trip → 建立 docx → append paragraph → 驗證內容

**Pending (not yet automated)**
- [ ] browse_task pipeline (Playwright headless)
- [ ] Broken session rebuild (needs short timeout test)
- [ ] document_edit full flow via LINE（上傳檔案 → 編輯 → R2 → 回傳連結）

### After Running

- Report pass/fail count
- If failures: check server logs for details
- Reminder test needs ~60s for CronScheduler tick
- Some tests require LINE (marked in checklist)
