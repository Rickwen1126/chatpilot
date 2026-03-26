## 2026-03-26 00:18 — 倉庫價值最大化方向 + 部署分離規劃

**Goal**: 從盤點轉向倉庫系統整體價值提升，規劃主動推播 + 部署架構

**Done**:
- show_image tool（download ref → R2 → ResponseInjector → 使用者看到圖片）
- shinyipaint system prompt 加完整盤點 SOP workflow
- batch_image_analyze description 加「提交後不要重複 download」
- general-agent pipeline 加 web_search tool（排程任務可搜尋）
- _format_result 格式化 pipeline 結果為人話（不再 push raw dict）
- warehouse API URL 改 env var 可配置（WAREHOUSE_API_URL / WAREHOUSE_WEB_URL）
- shinyipaint model 升 gpt-5.2（信益商業用，用最好的）
- E2E checklist 全面更新（warehouse 17 actions + admin API + 盤點 E2E）
- Commits: `90cbbf6` ~ `9b36589`

**Decisions**:
- 盤點先 hold，優先做倉庫系統最大價值功能
- 信益相關 chatbot 用 gpt-5.2（最強），其他維持 gpt-4.1/gpt-5-mini
- 不確定的照片用 show_image 回傳給使用者確認（不用檔名 reference）
- 部署要分 staging / production（見 User Notes）

**State**: Branch `main`, commit `9b36589`. Server running port 2999.

**Next**:
- [ ] 主動推播：每日庫存摘要 → CronScheduler + general-agent + warehouse tool
- [ ] 出貨追蹤：後端出貨單 API → 比對新料 vs 舊料 → 推播提醒
- [ ] 餘料閒置警告：追蹤入庫時間 → 超過 N 天沒動 → 推播
- [ ] 常用料低庫存 threshold → 低於時推播
- [ ] 部署分離：Windows WSL2 production 環境建置
- [ ] 盤點 E2E 訓練（等 empty DB，hold）

**User Notes**:
- 業主老闆今天親自進倉庫看常用料庫存叫料 → 如果系統主動推播餘料狀況，可省掉這步
- 餘料回倉庫後被涼在一邊沒用（拿新料不用找、一定能用）→ 追蹤出貨單，發現一直拿新料不拿舊料就提醒
- 部署分離想法：
  - Staging: 個人 LINE bot → cloudflare tunnel → Mac（現在這樣）
  - Production: 另辦信益官方 LINE bot → cloudflare tunnel → Windows WSL2（幾乎不關機）
  - 穩定後才上雲端
  - LINE 一個帳號可建多個 Messaging API channel（每個 channel = 一個 bot）
  - chatpilot 支援多環境 — .env 換 LINE channel token 就好
- 信益商業用要給最好的 model → shinyipaint 用 gpt-5.2，不省成本

---

## 2026-03-25 09:41 — Warehouse tool + LINE bindings + SDK model 調查 + 盤點訓練準備

**Goal**: 統一 warehouse tool、設定 LINE 群組 chatbot binding、調查 SDK model 限制、準備 shinyipaint 盤點能力訓練

**Done**:
- Unified `warehouse` tool 取代 `warehouse_query`（15 actions）
- BatchImageVisionPipeline + batch_image_analyze tool
- SDK session event logger
- Hub 媒體處理 + 私訊 busy buffer
- LINE route binding 設定 + admin API
- rick-assistant / family-helper chatbot
- SDK 0.2.0 升級
- E2E CLI_TIMEOUT 60s

**Decisions**:
- warehouse tool action dispatch 一個 tool 包全部 API
- Claude models 在 SDK 不支援 binaryResultsForLlm
- gpt-5.4-mini 不在 SDK model list
- 盤點用互動對話模式

**State**: Superseded by 2026-03-26 entry.

**User Notes**:
- SDK binary支援表/model限制 → 見 CLAUDE.md
- JSON Schema array 必須有 items 定義
- 訓練計畫：用 empty DB + E2E 模擬盤點
