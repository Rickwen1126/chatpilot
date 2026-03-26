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
- [ ] Group "bot /chatbot list" → keyword + slash command works
- [ ] Group @Bot /chatbot list → slash command works
- [ ] Busy gate (group): second mention while processing → "處理中" reply
- [ ] Auto-trigger: 群組訊息含 chatbot auto_trigger_keywords → 自動觸發（不需 @bot）
- [ ] Auto-trigger 只對 binding 到該群組的 chatbot keywords 生效（不跨 bot）
- [ ] Auto-trigger + 通用 trigger_keywords 並存（prefix vs anywhere）
- [ ] 群組訊息不含任何 trigger → context buffer（靜默）
- [ ] Busy gate (private): busy 中的訊息進 context buffer 不丟棄，idle 後 drain

**Adapters**
- [ ] LINE private chat → chatbot responds
- [ ] LINE group @bot → chatbot responds
- [ ] LINE reply token expired → fallback to push
- [ ] LINE image → [圖片 ref:line:{id}] in context buffer (不觸發 chatbot)
- [ ] LINE audio → [音檔 ref:line:{id}] in context buffer (不觸發 chatbot)
- [ ] LINE file → [檔案 ref:line:{id}:{filename}] in context buffer (不觸發 chatbot)
- [ ] LINE image + 文字 follow-up → chatbot 同時看到圖片 ref + 文字（context drain）
- [ ] LINE @bot "剛那張圖是什麼" → LLM calls download_media

**Memory Store**
- [ ] save_memo → LLM asks confirmation → stores in SQLite
- [ ] list_memos → shows saved memos
- [ ] delete_memo → removes memo
- [ ] save_custom_prompt → stores preference + marks needs_rebuild
- [ ] Session rebuild after custom_prompt → new system_message includes preference

**Reminder + Schedule**
- [ ] add_reminder → stored with due_at
- [ ] CronScheduler tick → due reminder enqueues general-agent task
- [ ] Reminder general-agent task → completed + push 人話結果（非 raw dict）
- [ ] schedule_task_cron → stored with tool_name + next_run_at
- [ ] schedule_task_cron invalid tool_name → rejected with available tools list
- [ ] CronScheduler tick → due schedule triggers pipeline via tool_name
- [ ] list_schedules → shows pending reminders + schedules (tool_name)
- [ ] cancel_schedule by index → deletes correct item

**General Agent Pipeline**
- [ ] general-agent pipeline registered at startup with web_search tool
- [ ] general-agent 排程任務能用 web_search 搜尋（非回覆「無法查詢」）
- [ ] Schedule with general-agent → CronScheduler → RunnerPool → SDK session → push
- [ ] general-agent timeout 300s（複雜任務需多次 web_search + 綜合分析）
- [ ] 排程 prompt 簡潔聚焦（避免一次要求太多導致 timeout）
- [ ] hub.receive_pipeline_result(direct) → push to user
- [ ] CronSchedulerConfig.available_tools from routes.yaml
- [ ] Pipeline 結果 push 格式化為人話（_format_result 不回 raw dict）
- [ ] browser-search pipeline 用真實 Chrome CDP（非 headless Playwright）
- [ ] browser-search Google 搜尋回傳結果（selector: a:has(h3)）

**Batch Image Vision Pipeline**
- [ ] batch_image_analyze tool enqueue → batch-image-vision pipeline 執行
- [ ] Pipeline SDK session 用 gpt-5.2 + download_media tool 看圖
- [ ] ≤5 張照片 chatbot 自己 download_media 看（不觸發 batch tool）
- [ ] >5 張照片 chatbot 呼叫 batch_image_analyze（不自己重複 download）
- [ ] Pipeline 結果 push 格式化分析文字（非 raw dict）

**Pipeline Result Routing (Hub)**
- [ ] receive_pipeline_result(direct) → immediate push (no busy gate)
- [ ] Pipeline result queue + drain infrastructure exists (Phase 2: via_chatbot)

**Browser Tools (Chrome CDP)**
- [ ] browser_navigate → 開啟 URL，回傳頁面 title 確認
- [ ] browser_navigate 空 URL → 回失敗訊息
- [ ] browser_eval → 執行 JS 提取頁面資料（如搜尋結果標題）
- [ ] browser_eval 壞 JS → 回 failure（不 crash）
- [ ] browser_eval retry 不同 selector → agent 可自行探索頁面結構
- [ ] browser_tabs → 列出分頁（* 標示目前）
- [ ] browser_tabs focus → 切換到指定分頁
- [ ] Chrome 自動啟動 → 沒有 running instance 時 start.js 自動起
- [ ] Chrome port 動態讀取 → 從 registry.json 讀，不寫死
- [ ] Google 搜尋不被擋 → 真實 Chrome profile，非 headless

**Workspace**
- [ ] Chatbot session → 自動建 data/workspace/{session_id}/ 目錄
- [ ] Pipeline session → 自動建 data/workspace/pipeline-agent-xxx/ 目錄
- [ ] SDK working_directory 生效 → LLM 建檔落在 workspace 而非 server cwd
- [ ] Config workdir 覆蓋 → chatbot 設定 workdir 後用指定路徑

**Warehouse Tool (unified)**
- [ ] action=search → 搜尋物料名稱/品牌/色號，回傳位置+數量（不自動附圖）
- [ ] action=search 結果包含 [位置圖可用: unit: URL] 供 chatbot 判斷
- [ ] action=get_items 無 layer → GET /units/{uid}/items 全層
- [ ] action=get_items 有 layer → GET /units/{uid}/layers/{layer}/items
- [ ] action=get_items 結果包含 [位置圖 URL] 供 chatbot 判斷
- [ ] action=get_inventory → 回傳庫存快照摘要
- [ ] action=search_materials → 搜尋物料目錄
- [ ] action=lock → 鎖定單一區域（需 unit_id 驗證）
- [ ] action=unlock → 解鎖單一區域（需 unit_id 驗證）
- [ ] action=lock_all → PUT /units/lock-all 一次鎖全部
- [ ] action=unlock_all → PUT /units/unlock-all 一次解鎖全部
- [ ] action=list_locked → 列出鎖倉中的區域
- [ ] action=add_item → 新增 item（需 unit_id 驗證）
- [ ] action=update_item → 更新 item（需 item_id 驗證）
- [ ] action=delete_item → 刪除 item（需 item_id 驗證）
- [ ] action=move_item → 移動 item（需 item_id 驗證）
- [ ] action=replace_layer → PUT 替換整層 items（盤點寫入）
- [ ] action=batch_items → POST 批次建立 items（傳 array）
- [ ] action=upload_image → 上傳照片到倉庫 API
- [ ] 缺少必要參數時回傳清楚錯誤訊息（不送空 ID 給 API）
- [ ] JSON Schema array type 有 items 定義（否則 Copilot API 400 reject）

**Show Image Tool**
- [ ] show_image(url=...) → 直接注入已有圖片 URL（位置圖）→ 使用者收到圖片
- [ ] show_image(ref=line:xxx) → download → R2 upload → 注入 → 使用者收到圖片
- [ ] show_image 空參數 → 回失敗訊息
- [ ] 使用者問「K1 在哪裡」→ chatbot 呼叫 warehouse get_items → 看到位置圖 URL → show_image(url) 回傳
- [ ] 純查數量時不附圖（chatbot 判斷，不自動注入）
- [ ] per-unit 位置圖 41 張（data/unit_images.json → R2 URL mapping）

**Admin API**
- [ ] GET /cli/routes → 列出所有已知 route + label + chatbot binding
- [ ] POST /cli/routes/sync → LINE API 自動同步群組名稱+人數
- [ ] POST /cli/routes/label → 設定/移除 route 標籤
- [ ] route binding 正確：user_id match > group_id match > platform match > default

**SDK Model 限制（已知，需持續驗證）**
- [ ] gpt-5.4-mini 不在 SDK model list（fallback 到 claude-sonnet-4.6，靜默）
- [ ] Claude models (haiku-4.5, sonnet-4.6) 不支援 binaryResultsForLlm（timeout）
- [ ] gpt-5.2-codex 不支援 binaryResultsForLlm
- [ ] Binary image OK: gpt-4.1, gpt-5-mini, gpt-5.1, gpt-5.2, gpt-5.3-codex, gemini-3-pro-preview

**Session**
- [ ] Server restart → resume_session preserves conversation history
- [ ] Broken session (timeout) → next message creates new session
- [ ] Config hot reload → routes.yaml change takes effect without restart

**Shinyipaint Tools**
- [ ] quote_search → 切 shinyipaint chatbot，查詢虹牌報價，回傳歷史資料
- [ ] document_edit xlsx round-trip → 建立 xlsx → append rows → 驗證內容
- [ ] document_edit docx round-trip → 建立 docx → append paragraph → 驗證內容

**Shinyipaint 盤點流程（互動式 E2E — 待 empty DB）**
- [ ] 「開始盤點 K1」→ chatbot 呼叫 warehouse lock + get_items
- [ ] 傳 1-3 張照片 + 文字描述 → chatbot 用 download_media 看圖 + 理解語義
- [ ] 傳 >5 張照片 → chatbot 呼叫 batch_image_analyze（不自己重複下載）
- [ ] chatbot 比對 DB 現有資料 → 產出差異表
- [ ] chatbot 跟使用者確認 → 正確後呼叫 replace_layer 寫入
- [ ] chatbot 呼叫 unlock 解鎖
- [ ] 整個流程不雞婆（不推銷下一步、不假設功能）
- [ ] Tool description 夠清楚（LLM 不會用錯 tool 或傳錯參數）
- [ ] System prompt 有盤點 SOP workflow 引導

**Observer Mode**
- [ ] Observer route 訊息 → 不回話（無 chatbot response）
- [ ] Observer route @mention → 還是不回話（observer 優先）
- [ ] 訊息進 context_buffer（count 遞增，log: [observer] buffered N/batch）
- [ ] context_window = max(context_window, observer_batch_size)
- [ ] 累積未達 batch_size → 不觸發
- [ ] 累積達 batch_size → 觸發 LLM 整理（log: batch triggered, draining, buffer now=0）
- [ ] LLM 回傳 JSON entries（category/who/content/timestamp）
- [ ] 閒聊被跳過（不出現在 entries）
- [ ] 整理結果存入 memory_observations table
- [ ] Drain 後 buffer 清空 → 重新累積第二批
- [ ] query_observations(source, category) → 回傳觀察紀錄
- [ ] query_observations(category="請假") → 只回該分類
- [ ] Cross-chat query：buddy chatbot 查 observer 群組資料 → 成功
- [ ] observer_mode=false 的 chatbot → 正常回話不受影響

**Pending (not yet automated)**
- [ ] browse_task pipeline (Playwright headless)
- [ ] Broken session rebuild (needs short timeout test)
- [ ] document_edit full flow via LINE（上傳檔案 → 編輯 → R2 → 回傳連結）
- [ ] receive_pipeline_result(via_chatbot) → queue if busy → drain on idle → chatbot processes → push (Phase 2)
- [ ] Pipeline result queue drain under concurrent user messages
- [ ] stt_transcribe tool（Whisper API — 語音轉文字）

### After Running

- Report pass/fail count
- If failures: check server logs for details (`grep "[event]\|ERROR" /tmp/chatpilot.log`)
- Reminder test needs ~60s for CronScheduler tick
- Some tests require LINE (marked in checklist)
- Shinyipaint 盤點 E2E 需要 empty DB server
