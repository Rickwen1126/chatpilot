# Docs Index

- Created: 2026-04-08
- Last Updated: 2026-04-08
- Status: active

這份索引用來說明 `docs/` 的頂層分類，以及目前 canonical / active 文件放在哪裡。

## 命名規則

- canonical 文件：
  - 固定檔名，如 `spec.md`、`plan.md`、`tasks.md`
  - 檔頭必須有：
    - `Created`
    - `Last Updated`
    - `Status`
- 補充型文件：
  - 檔名尾端加日期，例如 `observer-only-tools-plan@2026-04-08.md`
- 資料夾：
  - 預設不加日期
  - milestone / snapshot / timeboxed 主題才使用 `_YYYYMMDD` 或等價日期後綴

## Active Topics

### `observer-vnext/`

observer route/group/profile/reply/processing 抽象的 canonical 基底。

- canonical:
  - [spec.md](/Users/rickwen/code/chatpilot/docs/observer-vnext/spec.md)
  - [plan.md](/Users/rickwen/code/chatpilot/docs/observer-vnext/plan.md)
  - [tasks.md](/Users/rickwen/code/chatpilot/docs/observer-vnext/tasks.md)

### `route-discovery-onboarding/`

`follow/join` pre-message onboarding 與 route binding source-of-truth 收斂。

- canonical:
  - [spec.md](/Users/rickwen/code/chatpilot/docs/route-discovery-onboarding/spec.md)
  - [plan.md](/Users/rickwen/code/chatpilot/docs/route-discovery-onboarding/plan.md)
  - [tasks.md](/Users/rickwen/code/chatpilot/docs/route-discovery-onboarding/tasks.md)
- supporting:
  - [source-of-truth-refactor@2026-04-07.md](/Users/rickwen/code/chatpilot/docs/route-discovery-onboarding/source-of-truth-refactor@2026-04-07.md)

### `observation-retrieval-v1/`

observer 的 DB-first retrieval 設計與實作。

- canonical:
  - [README.md](/Users/rickwen/code/chatpilot/docs/observation-retrieval-v1/README.md)
  - [spec.md](/Users/rickwen/code/chatpilot/docs/observation-retrieval-v1/spec.md)
  - [plan.md](/Users/rickwen/code/chatpilot/docs/observation-retrieval-v1/plan.md)
  - [tasks.md](/Users/rickwen/code/chatpilot/docs/observation-retrieval-v1/tasks.md)
- supporting:
  - [observer-only-tools-plan@2026-04-08.md](/Users/rickwen/code/chatpilot/docs/observation-retrieval-v1/observer-only-tools-plan@2026-04-08.md)

### `file-handle-center/`

File ingress / governance boundary 的 canonical 設計與實作記錄。

- canonical:
  - [spec.md](/Users/rickwen/code/chatpilot/docs/file-handle-center/spec.md)
  - [plan.md](/Users/rickwen/code/chatpilot/docs/file-handle-center/plan.md)
  - [tasks.md](/Users/rickwen/code/chatpilot/docs/file-handle-center/tasks.md)

## Supporting Categories

### `todo/`

按日期記錄的工作筆記、open questions、暫時決策與下一步。

### `reference/`

長期有效、可反覆引用的技術與架構參考。

### `plans/`

較早期或單次性的設計/交接文件。這裡通常不是目前 canonical implementation guide。
