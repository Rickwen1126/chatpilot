# SHIP: chatpilot v2 Technical Context Review

tags: [ship, chatpilot, python, fastapi, copilot-sdk]

## 1. Problem Statement
**問題**：確認 chatpilot v2 的技術棧選擇是否有知識盲點
**對象**：開發者（自己）
**成功條件**：所有技術決策都有理解基礎，無 [B]lock

## 2. Solution Space

技術棧延續 v1（Python 3.11+ / FastAPI / Copilot SDK），不需重新比較。
v1 已驗證此棧可行。v2 新增的是架構模式（Message Hub、Task Scheduler、
Tool Factory、Pipeline），不是技術棧變更。

## 3. 技術決策清單
| 決策點 | 選擇 | 原因 | 備選 |
|--------|------|------|------|
| 語言 | Python 3.11+ | v1 已驗證，async/await 成熟 | — |
| Web framework | FastAPI | v1 已驗證，async native | — |
| 型別系統 | Pydantic v2 | v1 已驗證，Protocol for interfaces | — |
| Agent SDK | github-copilot-sdk | 唯一選項（產品需求） | — |
| Task history 儲存 | SQLite WAL | 結構化查詢 + 持久化 + 無外部依賴 | JSON files（查詢困難）、PostgreSQL（過重） |
| Memory Tool 儲存 | JSON files | KV 操作，直觀 debug | SQLite（過重）、Redis（外部依賴） |
| Context buffer cold | JSON files | 簡單持久化 | SQLite |
| Task queue | In-memory | MVP 足夠，介面保留抽換 | Redis/RabbitMQ（非 MVP） |
| UUID 策略 | uuid4 | 標準，無外部依賴 | ULID、nanoid |
| Queue backpressure | max_size + reject | 小群組場景，100 夠用 | 優先級隊列（過度工程） |
| Context 注入 | 串接 user message | SDK 無 context API | system_message 動態改（不支援） |
| SDK process 模型 | 共用單一 CLI process | 已驗證，多 session 共用 | — |

## 4. 橫向掃描
已在 spec 階段完成（OpenClaw binding routing 參考）。

## 5. 知識風險標記

### [B]lock
無。

### [R]isky
無。（原有 2 個 R 在討論中解除）

- ~~R1: Context buffer 注入機制~~ → 確認串接 user message，降為 [N]
- ~~R2: 多 session resource 模型~~ → 確認共用 process，降為 [N]

### [N]ice-to-know
- Python 3.11+ / FastAPI / Pydantic v2（v1 已熟）
- github-copilot-sdk 基本使用（spike 已驗證）
- SQLite WAL mode（標準知識）
- uuid4（trivial）
- LINE SDK reply token / push API（v1 已踩過坑）
- Context buffer 結構化格式（LLM 基本能力）
- SDK 共用 process 模型（已驗證）

### Spike 計畫
不需要。

## 6. 開工決策
- [x] 所有 [B]lock 已解除（無 Block）
- [x] [B]lock ≤ 3 個（0 個）
- [x] Problem Statement 清晰
- [x] Solution Space 有比較過
- [x] 技術決策都有根據

**狀態**：可開工
