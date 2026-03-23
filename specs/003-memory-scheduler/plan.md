# Implementation Plan: Memory Store + Cron Scheduler

**Branch**: `003-memory-scheduler` | **Date**: 2026-03-22 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/003-memory-scheduler/spec.md`

## Summary

為 chatpilot gateway 新增兩個獨立核心元件：

1. **Memory Store**：per-conversation 持久化記憶，泛用 CRUD Protocol + SQLite 實作，
   支援 memo / custom_prompt / reminder / schedule 四種 type。
2. **Cron Scheduler**：定時掃描 Memory Store 中到期的 reminder 和 schedule，
   執行動作（push 通知 / 觸發 pipeline），追蹤完整生命週期（pending → running → completed / failed）。

設計原則：只新增模組，既有架構（Hub、Router、Chatbot、Adapter）零修改。

## Technical Context

**Language/Version**: Python 3.11+（沿用既有）
**Primary Dependencies**: FastAPI, Pydantic v2, aiosqlite, github-copilot-sdk（全部既有）
**Storage**: SQLite（複用 TaskStore 的 aiosqlite + WAL 模式）
**Testing**: pytest + pytest-asyncio, ruff
**Target Platform**: Self-hosted macOS/Linux, cloudflared tunnel
**Project Type**: Web service（webhook-based gateway）— 增量功能
**Performance Goals**: Cron tick 60 秒，reminder/schedule 精度到分鐘級
**Constraints**: 不修改既有模組邊界；Memory Store 和 Cron Scheduler 各自可獨立測試
**Scale/Scope**: MVP 每 route <100 筆記憶，全系統 <1000 排程

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| # | 原則 | 狀態 | 說明 |
|---|------|------|------|
| I | Inbound–Process–Outbound 資料流 | ✅ PASS | Memory Store 和 Cron Scheduler 都在 Process 層。Cron → hub.push() 走 Outbound。資料流不違反 |
| II | 平台無關核心 | ✅ PASS | Memory Store 和 Cron Scheduler 不知道平台存在。push 透過 hub（已有），adapter 差異被封裝 |
| III | Config-Driven Routing | ✅ N/A | 此功能不涉及路由。tool 列表在 chatbot config |
| IV | Agent 單一職責 | ✅ PASS | Memory Store = 單純 CRUD。Cron Scheduler = 單純 scan + dispatch。各自獨立 |
| V | SDK 透明整合 | ✅ PASS | tool 用 SDK ToolInvocation → ToolResult 標準格式。不包裝黑盒 |
| VI | 模組邊界 | ✅ PASS | 新增 memory/ 和 cron/ 兩個獨立 package。既有模組零修改。只在 lifespan 做接線 |
| VII | 繁體中文設計文件 | ✅ PASS | 本文件為繁體中文 |

**Gate 結果**：全部通過。

## Project Structure

### Documentation (this feature)

```text
specs/003-memory-scheduler/
├── plan.md              # 本文件
├── research.md          # Phase 0：待決事項研究
├── data-model.md        # Phase 1：Memory Store 資料模型
├── contracts/           # Phase 1：介面契約
│   ├── memory-store.md  # MemoryStore Protocol
│   └── cron-scheduler.md # CronScheduler 介面
├── quickstart.md        # Phase 1：開發者指南
└── tasks.md             # Phase 2：/speckit.tasks 產出
```

### Source Code (new modules)

```text
src/chatpilot/
├── memory/                     # Memory Store（新增）
│   ├── __init__.py
│   ├── protocol.py             # MemoryStore Protocol
│   ├── store.py                # SqliteMemoryStore 實作
│   └── types.py                # Memo, CustomPrompt, Reminder, Schedule schemas
├── cron/                       # Cron Scheduler（新增）
│   ├── __init__.py
│   ├── scheduler.py            # CronScheduler tick loop + lifecycle
│   └── parser.py               # 簡化 cron 表達式解析
└── tools/builtin/              # 新增 tool（既有目錄）
    ├── save_memo.py
    ├── list_memos.py
    ├── delete_memo.py
    ├── save_custom_prompt.py
    ├── list_custom_prompts.py
    ├── delete_custom_prompt.py
    ├── add_reminder.py
    ├── schedule_task_cron.py    # 避免與既有 submit_task 混淆
    ├── list_schedules.py
    └── cancel_schedule.py

tests/
├── unit/
│   ├── test_memory_store.py
│   ├── test_cron_scheduler.py
│   ├── test_cron_parser.py
│   └── test_memory_tools.py
└── integration/
    └── test_cron_memory_flow.py
```

### 既有模組影響（最小）

```text
src/chatpilot/
└── server/__init__.py          # lifespan 加 MemoryStore + CronScheduler 初始化 + tool 註冊
config/routes.yaml              # chatbot tools 列表加新 tool 名稱
```

## Constitution Re-Check (Post Phase 1 Design)

| # | 原則 | 狀態 | 設計驗證 |
|---|------|------|----------|
| I | Inbound–Process–Outbound | ✅ PASS | Memory Store 在 Process 層。Cron → hub.push() 走既有 Outbound。不新建 outbound 路徑 |
| II | 平台無關核心 | ✅ PASS | memory/ 和 cron/ 完全不 import adapter。push 走 hub |
| III | Config-Driven Routing | ✅ N/A | 不涉及路由 |
| IV | Agent 單一職責 | ✅ PASS | MemoryStore 只管 CRUD。CronScheduler 只管 scan + dispatch。tool 只管轉接 |
| V | SDK 透明整合 | ✅ PASS | tool handler 遵守 ToolInvocation → ToolResult |
| VI | 模組邊界 | ✅ PASS | 新增 memory/ 和 cron/，各自獨立測試。既有模組不改 |
| VII | 繁體中文 | ✅ PASS | 是 |

## Generated Artifacts

| 文件 | Phase | 說明 |
|------|-------|------|
| `plan.md` | — | 本文件 |
| `research.md` | 0 | 待決事項研究 |
| `data-model.md` | 1 | Memory Store 三個 type 的資料模型 |
| `contracts/memory-store.md` | 1 | MemoryStore Protocol |
| `contracts/cron-scheduler.md` | 1 | CronScheduler 介面 |
| `quickstart.md` | 1 | 開發者指南 |
