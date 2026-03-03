# 功能規格：通用 Agent Gateway MVP

**Feature Branch**: `001-agent-gateway-mvp`
**Created**: 2026-02-23
**Status**: Draft
**Input**: 建立通用的 channel ↔ Copilot SDK agent gateway 核心架構

## Clarifications

### Session 2026-03-03

- Q: Reply token 過期的回覆策略為何？ → A: Agent 開始處理時啟動計時器（10–20 秒，可設定）。若計時器觸發前尚未完成，立即用當前 reply token 回覆「處理中」通知，agent 結果暫存至 Pending Message Queue，等使用者下一則訊息攜帶新 reply token 時補送。Push API 保留為未來可選切換模式（非預設），原因是 LINE Business push 按收件人計費，群組場景下成本不可控。
- Q: 路由識別鍵與部署範圍如何界定？ → A: 路由鍵採複合格式 `(platform, conversation_id)`，platform 為平台標識（如 `line`），conversation_id 取代原 group_id（私聊時可為空或使用 user_id）。每個 Chatpilot instance 對應一個平台 Official Account（如一個 LINE Official Account）；如需服務多個 Official Account，各自部署獨立 instance。
- Q: Route Map 的設定機制為何？ → A: 設定檔（如 `routes.yaml`）+ 熱重載（hot reload）——修改後自動生效，不需重啟服務。原因：bot 加入群組前 conversation_id 無法預知，必須在執行期動態新增路由規則；要求重啟服務才能生效，在實務上不可接受。
- Q: Multi-turn 對話的 session 邊界為何？ → A: 每個 `(platform, conversation_id)` 對應一個具名 Copilot SDK session（`sessionId = "{platform}-{conversation_id}"`）。每則訊息到來時呼叫 `resume_session(id)`，SDK 自動管理上下文、歷史與 compaction，無需手動維護對話記錄。長期記憶（如 Chronicle）列為 post-MVP 延伸，現有架構可自然支援。
- Q: 已路由群組不命中關鍵字時的預設行為為何？ → A: 每條路由規則可選配一個 fallback agent（預設為空）。有 fallback 時，未命中關鍵字的訊息路由至 fallback agent；無 fallback 時靜默忽略。由設定決定，而非全域統一行為。
- Q: MVP 最低可接受的 logging 層級為何？ → A: 完整 request/response log——包含完整訊息內容、路由決策、agent 回應，每筆附 conversation_id 與 timestamp。本服務為本地自架，訊息無隱私疑慮，完整 log 有助於 debug 與日後診斷。

## User Scenarios & Testing *(mandatory)*

### User Story 1 — 透過聊天頻道與 AI Agent 對話 (Priority: P1)

使用者在任一已接入的聊天頻道（如 LINE 群組）發送文字訊息，
系統將訊息路由至對應的 AI agent，agent 透過 Copilot SDK
產生回應，再由頻道 adapter 將回應送回原頻道。

這是整個 gateway 的端到端核心流程。不依賴任何特定下游服務，
agent 可以是最基本的對話型 agent（echo 或 AI 回覆）。

**為何此優先級**：這是 gateway 存在的根本理由——打通
「頻道收訊 → 統一格式 → agent 處理 → 頻道回覆」的完整鏈路。
沒有此流程，其他功能皆無法運作。

**獨立測試方式**：從 LINE 群組發送一則訊息，確認收到 AI
agent 的回覆。可用簡單的 echo agent 或 Copilot SDK 預設
agent 驗證。

**驗收情境**：

1. **Given** LINE 群組已設定路由且 agent 已註冊，
   **When** 使用者在群組發送「你好」，
   **Then** 系統透過 Copilot SDK agent 產生回應並回覆至群組

2. **Given** 同上條件，
   **When** 使用者發送需要多輪推理的問題，
   **Then** agent 透過 Copilot SDK 的 planning / tool-calling
   能力處理後回覆結果

3. **Given** agent 處理過程中發生錯誤，
   **When** 錯誤來自 agent 或 SDK 層，
   **Then** 系統回覆使用者友善的錯誤訊息，不洩漏內部細節

---

### User Story 2 — 透過 CLI 直接與 Agent 互動 (Priority: P2)

開發者或管理者透過 CLI 工具直接向 agent 發送訊息，
不需要啟動 webhook server 或依賴任何聊天平台。
CLI 使用與聊天頻道完全相同的 Copilot SDK 核心，
確保行為一致。

**為何此優先級**：CLI 是開發、測試、除錯的關鍵路徑。
有了 CLI，開發者可以在本地快速驗證 agent 行為，
不需要設定 LINE webhook + tunnel 的完整鏈路。
也為未來的自動化腳本和 CI 測試提供入口。

**獨立測試方式**：在終端機執行 CLI 指令發送訊息，
確認收到與聊天頻道相同的 agent 回應。

**驗收情境**：

1. **Given** CLI 工具已安裝且環境變數已設定，
   **When** 使用者執行 CLI 指令並輸入「你好」，
   **Then** 系統輸出 agent 的回應至 stdout

2. **Given** 已註冊多個 agent，
   **When** 使用者透過 CLI 指定 agent 名稱並發送訊息，
   **Then** 訊息路由至指定 agent 並回傳結果

3. **Given** CLI 與聊天頻道使用相同 agent，
   **When** 對相同訊息分別透過 CLI 和 LINE 發送，
   **Then** 兩者收到語意相同的回應（格式可能因頻道不同而異）

---

### User Story 3 — 路由分派將訊息導向正確 Agent (Priority: P3)

系統根據路由規則（conversation_id 精確比對、關鍵字比對）
將訊息自動分派至正確的 agent。未匹配的訊息靜默忽略，
避免不必要的 AI 成本和使用者干擾。

**為何此優先級**：當系統擴展至多個 agent 時，路由分派
決定了「誰來處理這則訊息」。但在單一 agent 的 MVP 階段，
路由的主要價值在於控制「哪些群組/訊息該回應」——靜默忽略
無關訊息同等重要。

**獨立測試方式**：設定路由表將不同群組對應至不同 agent，
驗證訊息被正確分派；從未路由的群組發送訊息，確認系統不回應。

**驗收情境**：

1. **Given** 路由表設定群組 A → agent-x、群組 B → agent-y，
   **When** 群組 A 發送訊息，
   **Then** 訊息由 agent-x 處理並回覆

2. **Given** 路由表設定關鍵字「庫存」→ agent-warehouse，
   **When** 已路由群組發送包含「庫存」的訊息，
   **Then** 訊息由 agent-warehouse 處理

3. **Given** 群組 C 未在路由表中，
   **When** 群組 C 發送任何訊息，
   **Then** 系統完全不回應

4. **Given** 已路由群組但訊息未命中任何關鍵字且路由規則未設定 fallback agent，
   **When** 使用者發送「今天天氣好」，
   **Then** 系統不回應

---

### User Story 4 — 新增頻道 Adapter 不影響核心 (Priority: P4)

新增一個聊天頻道（如 Telegram）時，只需要實作該頻道的
adapter（收訊、發訊、簽章驗證），不需要修改任何 agent、
dispatcher 或 SDK 核心程式碼。

**為何此優先級**：這驗證了架構的可擴展性——核心不因頻道
增加而改動。MVP 階段以 LINE 為首個頻道，但此 story
確認架構設計正確，未來接 Telegram、Web 時零核心修改。

**獨立測試方式**：實作一個最簡單的 mock adapter（如 test
adapter），確認只需實作 adapter 介面即可接入系統，
核心程式碼無任何修改。

**驗收情境**：

1. **Given** 系統已有 LINE adapter 且運作正常，
   **When** 新增一個 test/mock adapter 並註冊至系統，
   **Then** 無需修改 dispatcher、agent 或 SDK 層任何程式碼

2. **Given** test adapter 已註冊，
   **When** 透過 test adapter 發送訊息，
   **Then** 訊息經相同 dispatcher 和 agent 處理後回覆

---

### 邊界情況

- 頻道 webhook 簽章驗證失敗時，拒絕請求且不處理訊息
- Copilot SDK / 模型服務不可用時，回覆使用者友善的錯誤訊息
- 訊息包含特殊字元、超長文字或空白內容時，不應導致系統崩潰
- 同一群組短時間內大量訊息時，系統逐筆處理不丟失訊息
- 路由表為空（無任何路由規則）時，所有訊息靜默忽略
- agent 回應超出頻道訊息長度限制時，系統適當截斷或分段發送
- 一對一私聊（非群組）訊息時，conversation_id 為空，
  系統依關鍵字路由或預設 agent 處理，行為與群組訊息一致
- Agent 開始處理時啟動逾時計時器（預設 20 秒，可設定）；
  計時器觸發時，立即用當前 reply token 回覆「處理中」通知，
  agent 結果暫存至 Pending Message Queue 等待補送
- Pending Message Queue 中的結果於使用者下一則訊息到來時
  自動前置補送，再處理新訊息
- Pending Message Queue 中的訊息若超過合理等待時間仍未
  送出（無後續訊息觸發），訊息靜默丟棄（MVP 不主動 push）
- Push API 模式作為未來可選設定保留，MVP 預設關閉；
  原因：LINE Business push 按收件人計費，群組場景成本不可控

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: 系統 MUST 定義統一訊息格式（`Message`），包含
  文字內容、使用者識別、平台標識（platform）、
  對話識別（conversation_id，私聊時可為空）、平台 context
- **FR-002**: 系統 MUST 定義統一回應格式（`Response`），包含
  文字內容及附件清單（MVP 階段僅支援文字）
- **FR-003**: 系統 MUST 提供頻道 adapter 介面，adapter 負責：
  接收平台 webhook → 轉換為 `Message` → 將 `Response` 轉回
  平台格式發送
- **FR-004**: 系統 MUST 實作至少一個頻道 adapter（LINE），
  包含 webhook 接收與訊息簽章驗證
- **FR-005**: 系統 MUST 實作路由分派器（dispatcher），路由鍵
  採複合格式 `(platform, conversation_id)`，依序以
  conversation_id 精確比對 → 關鍵字比對 → per-route fallback agent 進行路由；
  fallback agent 為每條路由規則的可選設定（預設為空），
  未設定 fallback 時靜默忽略未命中訊息
- **FR-005a**: 路由表 MUST 支援熱重載（hot reload）——修改設定檔後
  自動生效，不需重啟服務；原因：bot 加入新群組時 conversation_id
  在執行期才可知，重啟才能生效的機制在實務上不可接受
- **FR-006**: 系統 MUST 整合 Copilot SDK 作為 agent 執行引擎，
  支援 planning、tool calling、multi-turn 對話能力；session 以
  `(platform, conversation_id)` 為鍵具名建立，訊息到來時呼叫
  `resume_session()` 自動恢復上下文，SDK 負責 compaction，
  系統無需手動管理對話歷史
- **FR-007**: 系統 MUST 提供 agent 註冊機制，允許新增 agent
  時只需定義 agent 的 tool 與 prompt，不需修改核心框架
- **FR-008**: 系統 MUST 提供 CLI 工具，可直接向指定 agent
  發送訊息並取得回應，不需要啟動 webhook server
- **FR-009**: 系統 MUST 透過環境變數管理所有機敏設定
  （頻道 token、API endpoint 等），不可寫死於程式碼中
- **FR-010**: 系統 MUST 對未匹配路由的訊息靜默忽略（不回應、
  不消耗 AI token）
- **FR-011**: 系統 MUST 在 agent 或外部服務錯誤時，回傳
  使用者友善的錯誤訊息至來源頻道
- **FR-014**: 系統 MUST 將完整 request/response 記錄至 stdout，
  包含：webhook 收到的完整訊息內容、路由決策結果（命中規則 /
  fallback / 忽略）、agent 回應內容、錯誤 stack trace；
  每筆 log 附 `conversation_id` 與 timestamp。
  本服務為本地自架，訊息無隱私疑慮
- **FR-012**: 系統 MUST 於 agent 開始處理時啟動逾時計時器
  （預設 20 秒，可透過設定調整）；計時器觸發時 MUST 立即
  以當前 reply token 回覆「處理中」通知，並將 agent 結果
  暫存至 Pending Message Queue；下一則來自同群組或使用者的
  訊息到來時，MUST 優先補送暫存結果再處理新訊息
- **FR-013**: 系統 MUST 提供 Push API 模式作為可設定的切換
  選項（預設關閉），供未來按需啟用，不影響預設 Reply 流程

### Key Entities

- **Message**: 統一輸入格式——文字內容、使用者 ID、
  平台標識（platform，如 `line` / `telegram`）、
  conversation_id（群組對話識別，私聊時為空）、
  平台 context（如 reply token 等平台特有資料）
- **Response**: 統一輸出格式——文字內容、附件清單
  （MVP 僅文字）
- **Channel Adapter**: 頻道轉接器——負責平台協議轉換，
  實作統一介面即可接入系統。每個平台 Official Account
  對應一個 adapter 實例；多個 Official Account 需部署
  獨立 Chatpilot instance
- **Dispatcher**: 路由分派器——以複合鍵
  `(platform, conversation_id)` 查找路由，依序執行
  conversation_id 精確比對 → 關鍵字比對 → 預設處理
- **Agent**: AI 代理——由 Copilot SDK 驅動，擁有自己的
  prompt 與 tool 定義。接收 `Message`、回傳 `Response`
- **Route Map**: 路由表——以 `(platform, conversation_id)`
  為主鍵；每條規則包含：關鍵字→agent 對應清單、可選的 fallback
  agent（無關鍵字命中時使用）。未設定 fallback 的規則對未命中
  訊息靜默忽略。儲存於設定檔（如 `routes.yaml`），支援熱重載；
  bot 加入群組後可即時新增路由規則而無需重啟服務
- **Pending Message Queue**: 暫存佇列——當 reply token
  過期時暫存待送訊息，關聯至來源群組或使用者，等待下一個
  有效 reply token 到來時送出。MVP 為 in-memory，不需持久化

## 假設條件

- 每個 Chatpilot instance 對應一個 LINE Official Account，
  以單一組 Channel Secret + Channel Access Token 運作；
  如需服務多個 Official Account，各自部署獨立 instance
- LINE Official Account 與 Messaging API channel 已建立，
  可取得 Channel Secret 與 Channel Access Token
- 使用者已有 GitHub Copilot 訂閱（免費方案即可），
  可使用 Copilot SDK 的 agent 能力
- cloudflared tunnel 已設定完成，提供外部 HTTPS 入口
  供 LINE webhook 使用
- Copilot SDK 的 session 持久化自動提供跨訊息的對話記憶；
  長期記憶（如 Chronicle cross-session 查詢）列為 post-MVP 延伸
- MVP 階段不處理圖片、語音或檔案等非文字輸入
- 下游服務（如倉庫 API）的整合屬後續功能，
  MVP 僅需驗證 agent 可透過 tool calling 呼叫外部服務的架構

## 範圍外（MVP 不包含）

- 特定下游服務的完整整合（倉庫查詢、週報產生等屬獨立功能）
- Telegram / Web / 語音等非 LINE 頻道的 adapter 實作
  （但架構 MUST 支援未來擴展）
- 圖片、語音、檔案等非文字訊息處理
- 跨 session 對話記憶
- 使用者身份驗證或權限管理
- 訊息排隊或流量控制機制
- 管理後台或監控儀表板

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 使用者從 LINE 群組發送文字訊息後 10 秒內
  收到 AI agent 的回應
- **SC-002**: 開發者透過 CLI 發送訊息後 10 秒內收到
  與聊天頻道相同 agent 的回應
- **SC-003**: 未路由群組或未匹配訊息的靜默率達 100%
  （零誤觸發、零 AI token 消耗）
- **SC-004**: 新增一個 mock/test adapter 時，
  核心程式碼（dispatcher、agent、SDK 層）修改量為零行
- **SC-005**: agent 或外部服務錯誤時，100% 的失敗查詢
  回傳使用者友善的錯誤提示
