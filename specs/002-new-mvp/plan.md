# Implementation Plan: Agent Gateway MVP v2

**Branch**: `002-new-mvp` | **Date**: 2026-03-18 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/002-new-mvp/spec.md`

## Summary

Chat-driven AI agent gateway：chatbot 即時對話層 + async agent team（pipeline）
任務層。Message Hub 統一管理訊息進出（mention filter、busy/idle、context buffer），
Binding Router 以特異性分數路由至正確 chatbot，Task Scheduler 管理異步任務排程，
Tool Factory 中央註冊所有 tool 並控制存取級別。

基於 v1 架構（`001-agent-gateway-mvp`）重構，保留 Python 3.11+ / FastAPI / Copilot SDK
技術棧，新增 Message Hub、Task Scheduler、Tool Factory、Pipeline 框架等核心模組。

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: FastAPI, Pydantic v2, github-copilot-sdk, line-bot-sdk, watchdog, pyyaml, uvicorn, aiosqlite
**Storage**: In-memory（MVP）；SQLite（task history）；disk JSON（context buffer cold layer）
**Testing**: pytest + pytest-asyncio, ruff（linting）
**Target Platform**: Self-hosted macOS/Linux, cloudflared tunnel 暴露 webhook
**Project Type**: Web service（webhook-based gateway）
**Performance Goals**: Chatbot 回應 <3s（SC-001）、任務確認 <1s（SC-002）、push 結果 <5s（SC-003）
**Constraints**: Webhook 非阻塞處理並行請求、chatbot 對話不被 task blocking
**Scale/Scope**: 小群組 / 1:1 私聊、單一 LINE Official Account、concurrent_runners 1~4

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| # | 原則 | 狀態 | 說明 |
|---|------|------|------|
| I | Inbound–Process–Outbound 資料流 | ✅ PASS | Adapter（inbound）→ Message Hub → Chatbot/Pipeline（process）→ Adapter（outbound）。三段分離清晰 |
| II | 平台無關核心 | ✅ PASS | 統一 Message/Response 契約。Adapter 吸收平台差異，核心不知道 LINE 存在 |
| III | Config-Driven Routing | ✅ PASS | Binding + match_weights 分數表。可擴展新維度不改 code |
| IV | Agent 單一職責 | ✅ PASS | Pipeline node 各自獨立 session、單一任務。大任務由 pipeline 組合 |
| V | SDK 透明整合 | ✅ PASS | Agent 擁有自己的 session config。SDK 功能直接暴露，不包黑盒 |
| VI | 模組邊界 | ✅ PASS | Adapter / Hub+Router+Scheduler / Agent 三層可獨立測試 |
| VII | 繁體中文設計文件 | ✅ PASS | 所有 speckit 文件皆繁體中文 |

**Gate 結果**：全部通過，無違反。可進入 Phase 0。

## Project Structure

### Documentation (this feature)

```text
specs/002-new-mvp/
├── plan.md              # 本文件
├── research.md          # Phase 0：待決事項研究結果
├── data-model.md        # Phase 1：資料模型
├── quickstart.md        # Phase 1：開發者快速上手指南
├── contracts/           # Phase 1：介面契約
│   ├── adapter.md       # ChannelAdapter Protocol
│   ├── message-hub.md   # MessageHub Protocol
│   ├── tool-factory.md  # ToolFactory Protocol
│   ├── scheduler.md     # TaskScheduler Protocol
│   ├── pipeline.md      # PipelineNode Protocol
│   └── webhook-api.md   # Webhook HTTP API
└── tasks.md             # Phase 2：/speckit.tasks 產出
```

### Source Code (repository root)

```text
src/chatpilot/
├── __init__.py
├── core/                    # 核心型別與設定
│   ├── types.py             # Message, Response, ChatRoute, TaskInfo
│   ├── errors.py            # 統一錯誤型別
│   └── config.py            # Config loader（YAML → Pydantic models）
├── hub/                     # Message Hub（中央訊息處理中心）
│   ├── __init__.py
│   ├── protocol.py          # MessageHub Protocol
│   ├── hub.py               # InMemoryMessageHub 實作
│   ├── context_buffer.py    # ContextBuffer（sliding window + disk flush）
│   └── mention_filter.py    # 群組 @bot mention 偵測
├── routing/                 # Binding Router
│   ├── __init__.py
│   ├── binding.py           # Binding 型別 + match_weights 計分
│   └── router.py            # BindingRouter（config → chatbot 對應）
├── chatbot/                 # Chatbot Session 管理
│   ├── __init__.py
│   ├── session.py           # ChatbotSession（SDK session wrapper）
│   └── manager.py           # ChatbotManager（per-route session pool）
├── tools/                   # Tool Factory（中央 tool 註冊）
│   ├── __init__.py
│   ├── factory.py           # ToolFactory（註冊、存取控制、產出）
│   ├── registry.py          # ToolRegistry（tool 定義儲存）
│   └── builtin/             # 內建 tool 實作
│       ├── __init__.py
│       ├── task_history.py  # 任務歷史查詢 tool
│       └── submit_task.py   # 提交 async task 的 tool
├── scheduler/               # Task Scheduler
│   ├── __init__.py
│   ├── protocol.py          # TaskScheduler Protocol
│   ├── scheduler.py         # InMemoryTaskScheduler 實作
│   ├── runner.py            # RunnerPool（concurrent task execution）
│   └── store.py             # TaskStore（SQLite 持久化）
├── pipeline/                # Pipeline 框架
│   ├── __init__.py
│   ├── node.py              # PipelineNode Protocol
│   ├── executor.py          # PipelineExecutor（node chain 執行）
│   └── memory.py            # Memory Tool（跨 node 脈絡保留）
├── adapters/                # Channel Adapters
│   ├── __init__.py
│   ├── protocol.py          # ChannelAdapter Protocol
│   ├── line/                # LINE adapter
│   │   ├── __init__.py
│   │   ├── parser.py        # Webhook 解析 + 簽章驗證
│   │   └── adapter.py       # LINE Reply + Push API
│   └── mock/                # Mock adapter（測試用）
│       └── __init__.py
├── agents/                  # Pipeline agent 定義
│   ├── __init__.py
│   └── warehouse/           # 倉庫管理 agent
│       ├── __init__.py
│       └── db.py
├── sdk/                     # SDK session 輔助
│   ├── __init__.py
│   └── session.py           # SDK session 建立 / 生命週期
├── cli/                     # CLI 工具
│   ├── __init__.py
│   └── main.py
└── server/                  # FastAPI 應用
    ├── __init__.py
    ├── app.py               # FastAPI app factory
    └── webhook.py           # Webhook route handler（薄層）

tests/
├── unit/                    # 單元測試
│   ├── test_binding.py
│   ├── test_context_buffer.py
│   ├── test_mention_filter.py
│   ├── test_tool_factory.py
│   ├── test_scheduler.py
│   └── test_config.py
├── integration/             # 整合測試
│   ├── test_hub_flow.py
│   ├── test_task_lifecycle.py
│   └── test_pipeline.py
└── contract/                # 契約測試
    ├── test_adapter_contract.py
    └── test_message_types.py

config/
├── routes.yaml              # Binding + chatbot + agent + scheduler 設定
└── .env.example             # 環境變數範例
```

**Structure Decision**: 單一專案結構，以功能領域分 package（hub、routing、chatbot、
tools、scheduler、pipeline、adapters）。相較 v1 的 dispatch/processing/queue 分法，
v2 直接對應架構圖的模組名稱，降低認知負擔。

## Constitution Re-Check (Post Phase 1 Design)

| # | 原則 | 狀態 | 設計驗證 |
|---|------|------|----------|
| I | Inbound–Process–Outbound | ✅ PASS | Adapter protocol（inbound）→ MessageHub + Router + Chatbot/Pipeline（process）→ Adapter protocol（outbound）。contracts/ 明確分離三段 |
| II | 平台無關核心 | ✅ PASS | data-model.md 的 Message/Response 不含平台欄位。platform_context 為 opaque dict |
| III | Config-Driven Routing | ✅ PASS | Binding 型別定義 match_weights 計分。router.py 純計算，不硬編碼 |
| IV | Agent 單一職責 | ✅ PASS | PipelineNode Protocol 強制 single execute()。Pipeline 組合 nodes |
| V | SDK 透明整合 | ✅ PASS | SdkSessionNode 直接用 SDK session config。ToolFactory 提供 tools，不包裝 SDK |
| VI | 模組邊界 | ✅ PASS | 6 個 Protocol contracts 定義清晰邊界。每個可獨立測試 |
| VII | 繁體中文 | ✅ PASS | 所有設計文件為繁體中文 |

**Post-design gate 結果**：全部通過。

## Complexity Tracking

> 無 Constitution 違反，本節不適用。

## Generated Artifacts

| 文件 | Phase | 說明 |
|------|-------|------|
| `plan.md` | — | 本文件 |
| `research.md` | 0 | 10 項待決事項全部解決 |
| `data-model.md` | 1 | 12 個實體定義 + 關係圖 + 持久化策略 |
| `contracts/adapter.md` | 1 | ChannelAdapter Protocol |
| `contracts/message-hub.md` | 1 | MessageHub + ContextBuffer Protocol |
| `contracts/tool-factory.md` | 1 | ToolFactory Protocol + agent team tool 機制 |
| `contracts/scheduler.md` | 1 | TaskScheduler + TaskStore + RunnerPool |
| `contracts/pipeline.md` | 1 | PipelineNode + PipelineExecutor + MemoryTool |
| `contracts/webhook-api.md` | 1 | HTTP API endpoints |
| `quickstart.md` | 1 | 開發者快速上手指南 |
