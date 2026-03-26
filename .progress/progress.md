## 2026-03-26 11:25 — Browser tools + 位置圖 + Auto-trigger + 搜尋修正

**Goal**: 瀏覽器能力、位置圖整合、群組自動觸發、warehouse 搜尋行為修正

**Done**:
- shinyipaint auto_trigger 加「阿信」alias
- 倉庫容量欄位建議文件 `docs/plans/warehouse-capacity-field.md`（待後端處理）
- Observer + cross-chat 架構設計討論完成
- browser_navigate / browser_eval / browser_tabs tools — 真實 Chrome CDP 操作
- browser-search pipeline 改用 iso-browser Chrome（非 Playwright headless）
- Google search selector 更新（div.g → a:has(h3)），Chrome 動態 port
- show_image 支援 url + ref 雙模式
- 41 張 per-unit 位置圖上傳 R2（data/unit_images.json mapping）
- warehouse search/get_items 結果帶位置圖 URL，chatbot 問位置時用 show_image 回傳
- ResponseInjector 恢復 deep link 注入（搜尋結果不帶文字 URL，由 injector 附加）
- 搜尋預設排除鎖倉區域 + 附帶鎖倉提示
- include_locked description 明確說預設 false
- per-chatbot auto_trigger_keywords（群組訊息任意位置 match → 觸發 bound chatbot）
- buddy + shinyipaint 加 browser tools
- shinyipaint auto_trigger: 龍泰/303/立邦/得利/虹牌/查詢/庫存/倉庫/入庫/出庫/幾桶/幾罐/有沒有/在哪/報價/盤點/水泥漆/乳膠漆/油漆
- general-agent pipeline timeout 120s → 300s
- 高小子排程改 general-agent + prompt 簡化
- 清除所有測試排程
- 21/21 E2E 全過
- Commits: `9b36589` ~ `f8c2966`

**Decisions**:
- Browser tools 給 agent 自行探索能力（navigate + eval + tabs），壞了能 retry 不同 selector
- iso-browser Chrome 動態 port（從 registry.json 讀，不寫死）
- auto_trigger 只對 binding 到該群組的 chatbot keywords 生效
- 搜尋不自動附圖，只有問位置才 show_image
- Observer 是 chatbot 的 mode 設定（不是新元件），任何 chatbot 都能開啟
- Observer + keyword auto_trigger 並存：keyword = 快速 filter，Observer = 智慧補漏
- 容量應是獨立欄位（capacity + capacity_ml），不塞 description

**State**: Branch `main`, commit `f8c2966`. Server running port 2999.

**Next**:
- [ ] Observer mode — chatbot config 加 mode: observer（靜默收集 + batch 整理 + 結構化存 DB）
- [ ] Cross-chat query — query_observations tool（跨群組查觀察資料，config 控權限）
- [ ] 主動推播：每日庫存摘要 / 低庫存警告 / 餘料閒置
- [ ] 出貨追蹤：後端出貨單 API → 新料 vs 舊料比對
- [ ] 後端 capacity 欄位（等後端改）→ chatpilot warehouse tool 接上
- [ ] 盤點 E2E 訓練（等 empty DB）
- [ ] 部署分離：staging / production

**User Notes**:
- Observer 完整 user story：信益大群組（幾十人）→ bot 進去只觀察不發言 → 每 N 則整理一次存 DB（分類：請假/進料/出料/工程進度）→ 管理群組或 Rick 私訊可用 query_observations 查「員工請假狀況」「進出料狀況」
- Observer 是 chatbot 的 mode 設定，不是新元件。以後任何 chatbot 都可以邊回話邊觀察（但目前沒想到具體需求，先做 silent observer）
- Cross-chat 權限：config 設定 source_group + allowed_consumers
- 「阿信」是 shinyipaint 的 alias，加在 auto_trigger_keywords
- 容量欄位建議文件在 `docs/plans/warehouse-capacity-field.md`，待後端處理
- Cloudflare tunnel 需要手動確認存活，多次斷線未察覺

---

## 2026-03-26 00:18 — 倉庫價值最大化方向 + 部署分離規劃

**Goal**: 從盤點轉向倉庫系統整體價值提升，規劃主動推播 + 部署架構

**Done**:
- show_image tool, shinyipaint SOP prompt, batch_image_analyze description
- general-agent + web_search, _format_result 人話格式化
- warehouse API URL env var, shinyipaint model gpt-5.2
- E2E checklist 全面更新

**State**: Superseded by 2026-03-26 11:25 entry.

**User Notes**:
- 業主老闆親自進倉庫看料 → 主動推播能省掉這步
- 餘料追蹤：出貨單比對新料 vs 舊料
- 部署分離：staging Mac / production Windows WSL2
