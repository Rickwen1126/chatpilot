## 2026-03-23 15:56 — shinyipaint tools + 業主 demo + milestone 確認

**Goal**: 實作 quote_search + document_edit tools，demo 給業主，確認後續計畫

**Done**:
- quote_search tool — JSON 搜尋歷史報價（building_type/area/brand/keyword），LINE demo 成功
- document_edit tool — .xlsx/.docx 編輯 via openpyxl/python-docx + R2 上傳
- LINE FileMessageContent parser — 產出 `[檔案 ref:line:{id}:{filename}]`
- 統一 tool call logging — `_to_sdk_tool()` wrap handler，所有 tool 印 `[tool_call]`/`[tool_result]`
- ChatbotManager debug log — session setup 印 tool list
- data/quotes/quotes.json — 8 筆模擬報價 + .gitignore exception
- 單元測試 28 個（quote_search 9 + document_edit 19），全 69 tests passing
- E2E checklist 更新 + run_e2e.sh 加 quote_search/document_edit 測試段
- python-docx + openpyxl 依賴加入 pyproject.toml
- Commits: `dbfe8c8` ~ `68598e9`

**Decisions**:
- document_edit 用 GLOBAL AccessLevel（同步流程），未來複雜版改 AGENT_TEAM_TRIGGER + pipeline
- R2Storage 在 lifespan 初始化，傳入 _register_tools
- worktree 開發 → merge 回 main（有 server/__init__.py conflict，已解）

**State**: Branch `main`, commit `68598e9`. Server 跑著 port 2999.

**Bugs discovered**:
- `session_id → route_id` 轉換 bug：`replace("-", ":", 1)` 只換第一個 dash，session_id 含 `-chatbotName` 後綴 → reminder/schedule push 失敗（route_id 多了 `-shinyipaint`）
- document_edit ref 解析：LLM 呼叫 download_media 而非 document_edit，且 download_media 收三段式 ref `line:id:filename` media_id 解析錯 → failure
- 倉庫搜尋精度：用戶說「黑色消光」但 DB 叫「平光 黑」，全文匹配不上（倉庫 API 端問題）

**Next**:
- [ ] 修 route_id 轉換 bug（影響所有 memory tools 的 push）
- [ ] 修 download_media 支援三段式 ref + system_message 引導 document_edit
- [ ] 倉庫盤點（3/25 前，用 warehouse-batch-inventory skill）
- [ ] observer bot — 大群組資訊觀察（物料位置、需求、整理）
- [ ] 王大叔出貨單記錄功能
- [ ] 報價單數位化流程（手寫照片→OCR→AI checklist 補關鍵字→存 DB）

**User Notes**:
- 3/25(三) milestone：倉庫系統正式開始使用，今天(3/23)只是 demo
- 倉庫 alignment 三管齊下：大群組觀察(自動) + 人工盤點(批次) + 王大叔出貨單
- 報價單痛點：業務寫「茶園」但後來問「某某工作室」，後勤找一整天。AI 在 key 單時用 checklist 補齊所有可搜尋關鍵字（地址、建設/設計公司、別名）
- observer bot feature 在 .bank/ 裡有定義
- quote_search 的 quotes.json 是 demo 用，正式版接報價數位化流程
- 請款抓漏需求：工期 2-3 年，分段請款不連續（例：請 1-5F，跳 6-7F，後請 8-10F），容易忘記請中間樓層。AI 做第二雙眼交叉驗證，不取代小姐工作。小姐抓的 < AI 的 → 回頭確認，雙面紗設計
- SOP 數位化：傳統油漆工法口耳相傳，拼圖式採集（現場語音問師傅+拍照錄影+老闆訪談→AI整理）。啟動待業主授權進場。TODO：晚上討論 SOP 文件的具體策略/做法

---

## 2026-03-23 08:33 — 003 Memory Store + Cron Scheduler 實作完成

**Goal**: 實作 Memory Store + Cron Scheduler（35 tasks），E2E 驗證

**Done**:
- 35/35 tasks complete, 41 tests passing
- memory/ package: types, protocol, SqliteMemoryStore（4 tables, WAL）
- cron/ package: parser（daily/weekly/interval）, CronScheduler（tick loop + lifecycle）
- 10 tools: save/list/delete_memo, save/list/delete_custom_prompt, add_reminder, schedule_task_cron, list_schedules, cancel_schedule
- ChatbotManager: resume-first session + needs_rebuild + custom_prompt injection
- E2E 全部驗證通過（見下方 User Notes）
- Commits: `a2df70d` ~ `8f3b95b`, pushed to `003-memory-scheduler`

**Decisions**:
- Resume-first session：先 try resume，失敗才 create。session_id 確定性（route_id 轉換），不需 persist
- Custom prompt 注入格式：base system_message + `\n\n[使用者偏好]\n- text1\n- text2`
- needs_rebuild 獨立於 broken（分開 log）
- schedule_task_cron input_data 必須包成 dict（Pydantic 驗證）

**State**: Branch `main`, commit `efbb3a1`, pushed. 41 tests, ruff clean. R2 + LINE 圖片回傳 E2E 驗證通過。

**Done (continued)**:
- Cancel schedule 改 index-based（不用 ID）
- trigger_keywords config-driven（`bot` 開頭觸發）
- lifespan() 拆分（抽 4 個 helper function）
- /e2e slash command + checklist（30+ 項）
- R2 storage 模組 + LINE ImageMessage 支援 + .env.example
- R2 驗證通過（upload + public fetch OK，有幾秒傳播延遲）

**Next**:
- [ ] browse_task E2E — 未驗證
- [ ] broken session rebuild — 未驗證

**User Notes**:
- 003 Memory Store + Cron Scheduler 全部實作完成 + E2E 驗證通過
- 記憶延續：server 重啟後 bot 仍記得「我叫 Rick」（resume_session 生效）
- Custom prompt 注入：使用者說「以後用英文」→ 存偏好 → session rebuild → 下則全英文回覆
- Reminder push：設定 1 分鐘後提醒 → CronScheduler 60s tick 掃到 → push 成功
- Schedule + list：設定 echo pipeline 每 2 分鐘 → list 顯示正確
- Cancel：LLM 傳了截斷的 ID 導致找不到，非 code bug，是 tool description 可以優化的地方
- R2 storage 驗證通過：upload OK、public fetch 200（有幾秒 CDN 傳播延遲，不影響使用）
- 圖片回傳功能已接上：R2 upload → Response.attachments → LINE ImageMessage。但還沒有觸發場景（需要 LLM 生成圖片的 tool 才能 E2E 測試）
- R2 Public Development URL 有 rate limit 警告，生產建議用 Custom Domain
- R2 + LINE 圖片回傳 E2E 成功：1.4MB JPG upload → R2 → LINE ImageMessage push → 使用者收到圖片
- R2 public fetch 有幾秒 CDN 傳播延遲，push 前 sleep 5s 解決
- E2E script 加入 R2 測試（有 config 時跑，沒有時 skip）
- 你的私聊 route_id：`line:Ufc68d77c84b42995d970dc6639da4316`

---

## 2026-03-22 23:31 — 003 spec 完成 + custom_prompt + 平台問題發現

**Goal**: Memory Store + Cron Scheduler spec/plan，加 custom_prompt type

**Done**:
- 003-memory-scheduler spec 加入 custom_prompt type（使用者偏好/習慣）
- Session needs_rebuild pattern 設計完成：custom_prompt 更新 → 標記 → 下則訊息重建 session
- Commit `ae0a5a3`

**Decisions**:
- custom_prompt 注入 system_message：session create 時合併，不是每輪注入
- needs_rebuild 複用 broken session eviction pattern，無 race condition（busy gate 序列化）
- Reminder 未來也走 pipeline 讓 chatbot 潤飾（MVP 先直接 push 原文）
- 圖床用 Cloudflare R2（免費 10GB/月 + 免費 egress），記在 plan.md Future Tasks
- 群組觸發關鍵字：`AI `（不分大小寫）+ `@bot mention` 並行，放 config 不放 adapter

**State**: Branch `003-memory-scheduler`, commit `ae0a5a3`. Spec/Plan/Research/DataModel/Contracts 全完成。待 `/speckit.tasks`。

**Next**:
- [ ] `/speckit.tasks` → 產出 tasks.md
- [ ] 實作 Memory Store + Cron Scheduler + custom_prompt
- [ ] 群組 trigger_keywords 功能（`routes.yaml` config-driven，跟 003 無關，獨立做）

**User Notes**:
- LINE 電腦版無法 @ bot（已知限制），需要關鍵字觸發作為替代方案
- 觸發方式設計：config `trigger_keywords: ["ai"]`，mention_filter.py 讀 config 檢查，全平台生效
- 這個跟 003 spec 無關，獨立處理

---

