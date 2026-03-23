# 功能規格：Memory Store + Cron Scheduler

**Created**: 2026-03-22
**Status**: Draft

## 一、產品定位

為 chatpilot gateway 新增兩個核心元件，讓 chatbot 具備「記住事情」和「定時執行」的能力。

- **Memory Store**：per-conversation 持久化記憶，chatbot 可透過 tool 存取 memo、reminder、排程等資料
- **Cron Scheduler**：定時掃描 Memory Store 中的排程型資料，到期時觸發對應動作並追蹤完成狀態

**設計原則**：
- 以增加新元件為主，不大幅修改既有模組（Hub、Router、Chatbot、Adapter）
- 既有元件只做最小接線（lifespan 註冊 + tool 註冊）

---

## 二、使用者情境

### US1：記住事情（Memo）

使用者在對話中叫 bot 記住某件事，之後可以查詢或刪除。

> User: 記住：下週三客戶會議改到 2 樓會議室
> Bot: 已記下。
> User: 我之前記了什麼？
> Bot: 你有 1 筆記錄：下週三客戶會議改到 2 樓會議室（3/20 記錄）

**場景**：
- 私聊：個人備忘
- 群組：群組共用備忘（綁定 route_id）

### US1b：使用習慣偏好（Custom Prompt）

使用者在對話中表達偏好或使用習慣，bot 偵測到後詢問是否記錄，記錄後影響 bot 的行為風格。

> User: 以後回答我都用繁體中文，簡潔一點
> Bot: 好的，要幫你記下這個偏好嗎？
> User: 好
> Bot: 已記錄。之後我會用繁體中文簡潔回答。

**場景**：
- 語氣偏好：「正式一點」「輕鬆一點」
- 格式偏好：「用列表回答」「不要太長」
- 方法論偏好：「搜尋時優先找官方文件」
- 習慣更新後，下一則訊息起生效（session 自動重建）

### US2：設定提醒（Reminder）

使用者叫 bot 在指定時間提醒某件事，bot 到期主動 push 通知。

> User: 提醒我明天下午 3 點開會
> Bot: 好的，已設定提醒：2026-03-23 15:00 開會
> （隔天 15:00）
> Bot: [主動推送] 提醒：開會

**場景**：
- 一次性提醒：到期 push 後完成
- 到期前一天預告（可選）：前一天 push 「明天有：開會」

### US3：定期排程任務（Scheduled Task）

使用者叫 bot 定期執行某個 pipeline，結果 push 回對話。

> User: 每天早上 8 點幫我查台股大盤
> Bot: 已排定每日任務：08:00 查台股
> （隔天 08:00）
> Bot: [主動推送] 台股大盤：18,234 (+0.5%)

**場景**：
- 重複排程：cron 表達式定義週期
- 取消排程：使用者可列出、刪除

### US4：查看和管理排程

使用者可查詢、取消 reminder 和 scheduled task。

> User: 我有哪些排程？
> Bot: 你有 2 個排程：
>   1. [reminder] 明天 15:00 開會
>   2. [schedule] 每日 08:00 查台股
> User: 取消第 2 個
> Bot: 已取消「每日 08:00 查台股」

---

## 三、功能需求

### Memory Store

- **FR-001**：提供泛用 CRUD 介面（save / get / list / delete），以 route_id + type + id 為唯一鍵
- **FR-002**：type 由開發者定義，每個 type 有對應的 Pydantic schema 做資料驗證
- **FR-003**：MVP 支援四個 type：memo、custom_prompt、reminder、schedule
- **FR-004**：提供 `query(type, **filters)` 方法供跨 route 查詢（不綁 route_id），給 Cron Scheduler 使用
- **FR-005**：特殊查詢需求以具名 method 約束（如 `query_due_before(datetime)`），不開放任意 SQL / filter
- **FR-006**：底層實作使用 SQLite，介面使用 Protocol 保持可替換性
- **FR-007**：所有 type 的 schema 欄位必須有 default 值，確保 schema 演進時舊資料可讀取

### Memo Type Schema

- **FR-008**：memo 欄位：id, route_id, text, tags（可選）, created_at
- **FR-009**：支援 list（by route_id）、save、delete

### Custom Prompt Type Schema

- **FR-008a**：custom_prompt 欄位：id, route_id, text, category（可選：tone / format / method / general）, created_at
- **FR-008b**：per-route 可有多條 custom_prompt，session 建立時全部合併注入 system_message
- **FR-008c**：custom_prompt 更新後，標記當前 session 為 `needs_rebuild`，下一則訊息觸發 session 重建（帶新 system_message）
- **FR-008d**：session 重建流程：`needs_rebuild` 是獨立於 `broken` 的第二個 eviction flag。兩者觸發條件不同（broken=SDK crash/timeout，needs_rebuild=custom_prompt 更新），eviction 邏輯相同（destroy → create new），log 分開記錄以區分重建原因
- **FR-008e**：custom_prompt 注入格式：base system_message + `\n\n[使用者偏好]\n` + 各條 custom_prompt text 以 `\n- ` 串接。範例：`{base}\n\n[使用者偏好]\n- 用繁體中文回答\n- 簡潔為主`

### Reminder Type Schema

- **FR-010**：reminder 欄位：id, route_id, text, due_at（UTC datetime）, status（pending/running/completed/failed）, last_error, created_at
- **FR-011**：status 狀態機：pending → running → completed / failed
- **FR-012**：一次性提醒：completed 後不再被 Cron Scheduler 掃到
- **FR-013**：支援 query_due_before(datetime) 跨 route 查詢到期的 reminder

### Schedule Type Schema

- **FR-014**：schedule 欄位：id, route_id, cron_expr, pipeline_name, input_data, status, last_run_at, next_run_at, last_error, created_at
- **FR-015**：重複排程：completed 後計算 next_run_at，重設 status=pending
- **FR-016**：cron 表達式 MVP 支援簡化格式（daily HH:MM、weekly DAY HH:MM、interval Nm/Nh）
- **FR-017**：支援 query_next_run_before(datetime) 跨 route 查詢到期的 schedule

### Cron Scheduler

- **FR-018**：定時 tick（預設每 60 秒），掃描 Memory Store 中到期的 reminder 和 schedule
- **FR-019**：掃到到期項目 → 標記 status=running → 執行動作 → 根據結果標記 completed/failed
- **FR-020**：reminder 到期動作：hub.push(route_id, 提醒文字)
- **FR-021**：schedule 到期動作：透過既有 scheduler.enqueue 觸發 pipeline，pipeline 完成後結果由 RunnerPool push 回對話
- **FR-022**：失敗時記錄 last_error + 印 error log，不自動 retry
- **FR-023**：下次 scan 遇到 status=failed 的項目 → 印 warning log（讓開發者注意）
- **FR-024**：在 lifespan 啟動 / 停止，與 server 生命週期同步

### Tools（膠水層）

- **FR-025**：`save_memo` tool（GLOBAL）：LLM 呼叫存取 memo
- **FR-026**：`list_memos` tool（GLOBAL）：LLM 查詢 memo
- **FR-027**：`delete_memo` tool（GLOBAL）：LLM 刪除 memo
- **FR-027a**：`save_custom_prompt` tool（GLOBAL）：LLM 儲存使用者偏好/習慣。儲存後自動標記 session needs_rebuild
- **FR-027b**：`list_custom_prompts` tool（GLOBAL）：LLM 查詢已記錄的偏好
- **FR-027c**：`delete_custom_prompt` tool（GLOBAL）：LLM 刪除偏好。刪除後自動標記 session needs_rebuild
- **FR-028**：`add_reminder` tool（GLOBAL）：LLM 設定 reminder
- **FR-029**：`schedule_task` tool（GLOBAL）：LLM 設定定期排程
- **FR-030**：`list_schedules` tool（GLOBAL）：LLM 查詢排程和 reminder
- **FR-031**：`cancel_schedule` tool（GLOBAL）：LLM 取消排程或 reminder
- **FR-032**：所有 tool 自動帶入 route_id（從 invocation.session_id 推導：`session_id` 格式為 `{platform}-{conversation_id}`，替換第一個 `-` 為 `:` 得到 `route_id`）

---

## 四、既有模組影響評估

| 既有模組 | 影響 | 改動 |
|---------|------|------|
| Hub | 無 | 不動 |
| Router | 無 | 不動 |
| ChatbotSession | 無 | 不動 |
| ChatbotManager | 最小 | get_or_create_session 加 needs_rebuild 檢查（複用 broken pattern） |
| Adapters | 無 | 不動（push 已有） |
| ToolFactory | 最小 | 註冊新 tool（已有流程） |
| server/__init__.py | 最小 | lifespan 加 MemoryStore + CronScheduler 初始化 |
| config/routes.yaml | 最小 | chatbot tools 列表加新 tool 名稱 |

---

## 五、範圍界定

### 包含

- Memory Store Protocol + SQLite 實作
- 四個 type：memo、custom_prompt、reminder、schedule
- Cron Scheduler tick loop + 狀態追蹤
- 10 個 chatbot tool
- lifespan 接線

### 不包含

- 自訂 type runtime 建立（type 由開發者定義）
- 自動 retry 失敗的排程（MVP 只 log）
- 複雜 cron 表達式（MVP 用簡化格式）
- 跨 chatbot 記憶共享（記憶綁 route_id）
- Web UI 管理介面

---

## 六、成功標準

- **SC-001**：使用者透過 chatbot 存取 memo，存入後可查詢、可刪除
- **SC-002**：使用者設定 reminder，到期時收到主動 push 通知
- **SC-003**：使用者設定定期排程，到期時 pipeline 執行並 push 結果
- **SC-004**：排程執行失敗時有 error log 可查
- **SC-005**：新增 type 不需修改 Memory Store Protocol 或 Cron Scheduler 核心邏輯
- **SC-006**：既有模組（Hub、Router、Chatbot、Adapter）零修改

---

## 七、依賴與假設

### 依賴

- 既有 hub.push() 可主動推訊息到任何 route
- 既有 scheduler.enqueue() 可觸發 pipeline
- SQLite 已用於 TaskStore，可複用 DB 連線模式

### 假設

- 時間精度到分鐘級（60 秒 tick），不需秒級
- 時區：使用者輸入的時間由 LLM 解析為 UTC，系統內部全 UTC
- MVP 排程量小（<100 per route），不需索引最佳化
