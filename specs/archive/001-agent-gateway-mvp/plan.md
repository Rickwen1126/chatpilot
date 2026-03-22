# 實作計畫：通用 Agent Gateway MVP

**Branch**: `001-agent-gateway-mvp` | **Date**: 2026-03-03 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/001-agent-gateway-mvp/spec.md`
**Updated**: 2026-03-03 — 語言由 TypeScript 改為 Python（理由見 research.md）

**Note**: 由 `/speckit.plan` 指令產出，後因技術決策調整為 Python。工作流程參見 `.specify/templates/plan-template.md`。

---

## 摘要

建立通用的 channel ↔ Copilot SDK agent gateway 核心架構。採 **Python 3.11+ / FastAPI + uvicorn** 作為 webhook server；以 `github-copilot-sdk` 驅動 agent 執行引擎，session 以 `"{platform}-{conversation_id}"` 為鍵自動管理對話記憶；路由表存於 `routes.yaml` 並支援熱重載；逾時機制（20 秒計時器 + Pending Message Queue）確保 LINE reply token 在 60 秒有效期內完成首次回覆。

---

## 技術背景

**Language/Version**: Python 3.11+（Copilot SDK 最低需求）
**Package Manager**: `uv`（Rust-based，取代 pip/poetry）
**Primary Dependencies**:
- `github-copilot-sdk` — Copilot SDK agent 執行引擎（session 管理、tool calling、multi-turn）
- `line-bot-sdk` — LINE Messaging API（webhook parsing、簽章驗證、reply/push）
- `fastapi` — ASGI webhook server（Pydantic-native，async-native）
- `uvicorn` — ASGI server（生產級效能）
- `pydantic` v2 — 資料模型與 schema 驗證（FastAPI 內建整合）
- `watchdog` — `routes.yaml` 熱重載（跨平台 file system monitoring）
- `pyyaml` — YAML 解析
- `python-dotenv` — `.env` 環境變數載入

**Storage**: in-memory（Pending Message Queue）+ `routes.yaml` 檔案（路由設定）
**Testing**: `pytest` + `pytest-asyncio`（單元 + 整合）+ `httpx`（FastAPI TestClient）
**Linting**: `ruff`（linter + formatter）
**Target Platform**: Linux server（自架）+ cloudflared tunnel
**Project Type**: web-service + CLI
**Performance Goals**: reply latency < 10 秒（SC-001、SC-002）
**Constraints**:
- LINE reply token TTL：60 秒（官方），20 秒計時器提供 40 秒安全邊際
- Pending Queue：in-memory，不持久化（MVP 可接受）
- 單一 LINE Official Account per instance

**Scale/Scope**: 單一 LINE Official Account，MVP 單一群組驗證

---

## Constitution Check

*GATE：Phase 0 研究前必須通過；Phase 1 設計後再次確認。*

| 原則 | 檢查 | 說明 |
|------|------|------|
| I. 三層架構 | ✅ PASS | `src/chatpilot/channels/`（Channel）→ `src/chatpilot/dispatch/`, `src/chatpilot/agents/`, `src/chatpilot/sdk/`（SDK）← `src/chatpilot/cli/`（CLI）；import 方向正確 |
| II. Channel-Agnostic Core | ✅ PASS | Agent 只接收 `Message`（不含 `platform_context`）；FR-001/FR-002 定義統一型別；FR-004 要求 adapter 封裝 LINE 細節 |
| III. Fast-Path Dispatch | ✅ PASS | 路由順序：conversation_id exact match（O(1)）→ keyword substring match（O(n)）→ fallback agent；FR-010 確保未匹配靜默忽略，零 AI token 消耗 |
| IV. Ports & Adapters | ✅ PASS | `ChannelAdapter` Protocol 於 `src/chatpilot/channels/adapter.py`；`BaseAgent` Protocol 於 `src/chatpilot/agents/base.py`；Core 只依賴 Protocol，不依賴具體實作 |
| V. Independent Lifecycle | ✅ PASS | 各層可獨立部署；下游服務呼叫透過 tool interface 隔離 |
| VI. 文件語言 | ✅ PASS | 本文件以繁體中文撰寫；技術術語維持英文 |

**Phase 1 設計後 Re-check**：所有 contract 型別定義維持三層分離，無跨層 import 違規。✅

---

## 目錄結構

### 設計文件（本 feature）

```text
specs/001-agent-gateway-mvp/
├── plan.md              # 本檔案（/speckit.plan 產出）
├── research.md          # Phase 0 研究報告（/speckit.plan 產出）
├── data-model.md        # Phase 1 資料模型（/speckit.plan 產出）
├── quickstart.md        # Phase 1 快速入門（/speckit.plan 產出）
├── contracts/           # Phase 1 介面合約（/speckit.plan 產出）
│   ├── types.py         # 核心型別（Message、Response、RouteMap 等）
│   ├── channel_adapter.py  # ChannelAdapter Protocol
│   └── base_agent.py    # BaseAgent Protocol
└── tasks.md             # Phase 2 任務清單（/speckit.tasks 指令產出）
```

### Source Code（repo root）

```text
src/chatpilot/
├── __init__.py
├── core/
│   ├── __init__.py
│   ├── types.py           # 核心型別（Message、Response、RouteMap、PendingMessage）
│   └── errors.py          # 自定義 Exception（AgentError、RouteError 等）
│
├── channels/
│   ├── __init__.py
│   ├── adapter.py         # ChannelAdapter Protocol
│   └── line/
│       ├── __init__.py    # LINE adapter（ChannelAdapter 實作）
│       └── parser.py      # LINE webhook event → Message 解析
│
├── dispatch/
│   ├── __init__.py
│   ├── dispatcher.py      # 路由決策邏輯（三階段查找）
│   └── route_loader.py    # routes.yaml 載入 + watchdog 熱重載
│
├── agents/
│   ├── __init__.py        # AgentRegistry
│   ├── base.py            # BaseAgent Protocol
│   └── general/
│       └── __init__.py    # 範例 general-agent（Copilot SDK 驅動）
│
├── sdk/
│   ├── __init__.py
│   └── session_manager.py # CopilotClient wrapper；resume_session() 封裝
│
├── queue/
│   ├── __init__.py
│   └── pending_queue.py   # Pending Message Queue（in-memory dict）
│
├── server/
│   ├── __init__.py        # FastAPI 應用程式建立、webhook route 註冊
│   └── webhook.py         # /webhook/{platform} 路由 handler（逾時計時器）
│
└── cli/
    ├── __init__.py
    └── main.py            # CLI 進入點

config/
├── routes.yaml              # 路由設定（可熱重載，不納入版控）
└── routes.example.yaml      # 路由設定範本

tests/
├── conftest.py
├── unit/
│   ├── test_dispatcher.py
│   ├── test_route_loader.py
│   └── test_pending_queue.py
├── integration/
│   └── test_webhook.py
└── contract/
    └── test_adapter.py

.env.example
pyproject.toml
```

**結構決策**：採 `src/chatpilot/` layout（PEP 517 標準）。無前端、無獨立 API 服務；Channel Layer 與 Core Layer 在同一 Python process 中運行，透過函式呼叫邊界（而非 HTTP）隔離層次。

---

## Complexity Tracking

> 無 Constitution 違規，此區塊留空。
