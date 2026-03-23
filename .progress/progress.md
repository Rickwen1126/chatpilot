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

**State**: Branch `main`, commit `55f361c`, pushed. 41 tests, ruff clean.

**Done (continued)**:
- Cancel schedule 改 index-based（不用 ID）
- trigger_keywords config-driven（`bot` 開頭觸發）
- lifespan() 拆分（抽 4 個 helper function）
- /e2e slash command + checklist（30+ 項）
- R2 storage 模組 + LINE ImageMessage 支援 + .env.example
- R2 驗證通過（upload + public fetch OK，有幾秒傳播延遲）

**Next**:
- [ ] 圖片回傳 E2E：需要 LLM 生成圖片的場景觸發 → R2 upload → LINE ImageMessage
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

