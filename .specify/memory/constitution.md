<!--
Sync Impact Report
===================
- Version change: 2.1.0 → 2.2.0 (MINOR — further simplified,
  all design details in specs/PRDV2.md, constitution is pure principles)
- Templates requiring updates:
  - .specify/templates/plan-template.md — ⚠ pending (Constitution Check)
  - Others — ✅ no update needed
-->

# Chatpilot Constitution

## Core Principles

### I. Inbound–Process–Outbound 資料流

所有功能 MUST 遵守三段資料流邊界：

1. **Inbound** — 接收、驗證、轉為統一格式。不含業務邏輯。
2. **Process** — 路由、執行 agent、產出結果。
   所有 AI / 業務邏輯在此完成。
3. **Outbound** — 結果轉為平台格式，送回來源。

依賴方向 MUST 單向流入核心。Inbound/Outbound 層
MUST NOT 包含業務邏輯，Process 層 MUST NOT 依賴
任何特定平台實作。

### II. 平台無關核心

Agent 與路由邏輯 MUST NOT 存取平台專屬資料。
新增平台 MUST NOT 需要修改 agent、路由或 pipeline 程式碼。
平台差異由 adapter 層吸收，核心只認統一的
`Message` / `Response` 契約。

### III. Config-Driven Routing

訊息路由 MUST 由設定檔驅動，不可 hardcode。
路由匹配 MUST 以特異性分數決定優先級，不以順序。
分數規則 MUST 可擴展新維度而不需改 code。

### IV. Agent 單一職責

每個 agent session MUST 只做一件事，快速完成。
大任務 MUST 透過多 agent 組合完成，不由單一 agent 包辦。

### V. SDK 透明整合

Agent MUST 直接使用 SDK 能力，不得包裝成黑盒抽象。
Agent 擁有自己的 session config，gateway 不替 agent 決定。
SDK 功能 MUST 透明暴露，不被中間層截斷。

### VI. 模組邊界

核心邏輯 MUST 對外部平台與下游服務零直接依賴：

- **Adapter 層**（Inbound/Outbound）：平台專屬協議轉換，
  可獨立替換而不影響核心
- **Gateway 層**（Process）：路由、pipeline 執行、config 管理，
  不知道也不關心平台細節
- **Agent 層**（Process 內部）：業務邏輯與 SDK session，
  不知道也不關心自己被誰呼叫

各層 MUST 可獨立測試、獨立部署。層間契約透過統一型別
強制執行，不透過共享程式碼或緊耦合。

### VII. 繁體中文設計文件

所有 speckit 產出的設計文件 MUST 以繁體中文撰寫。
技術專有名詞維持英文，程式碼區塊與檔案路徑維持英文。

## Technology Constraints

| Constraint | Value |
|---|---|
| Agent SDK | GitHub Copilot SDK |
| Models | GPT-4.1 (free tier, default)；可依 config 指定 |
| Deployment | Self-hosted with cloudflared tunnel |
| Config | YAML；`.env` for secrets（MUST NOT commit） |

- 語言、runtime、web framework 為 plan-time 決定
- 新依賴 MUST 有正當理由
- Webhook MUST 非阻塞處理並行請求

## Development Workflow

- `Message` / `Response` 變更 MUST 審查向下相容
- Adapter 與 agent 程式碼 MUST 互不觸及
- 各層 MUST 可獨立測試
- `.env` MUST NOT commit

## Governance

本憲法為 Chatpilot 開發決策的最高權威文件。
衝突時憲法優先，除非先行正式修訂。

**修訂**：PR 提案 → 影響評估 → 版本更新。
**版本**：MAJOR = 原則重定義；MINOR = 新增/擴展；PATCH = 措辭。

**Version**: 2.2.0 | **Ratified**: 2026-02-22 | **Last Amended**: 2026-03-17
