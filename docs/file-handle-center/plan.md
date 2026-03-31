# FileHandleCenter Plan

## Goal

將 ChatPilot 目前分散的 file/media 處理，收斂成以 `FileHandleCenter` 為核心的正式治理邊界，並先完成最小可落地版本，支撐：

- adapter file ingress
- route-scoped file memory
- local materialization
- vision / STT / document 類流程
- 後續 tool / pipeline / agent generated files 的正式接入

## Scope

本輪目標是建立最小可運作骨架，不追求一次完成所有 file 相關重構。

### In Scope

- `SourceHandleInput` / `SourceFetchResult` 型別與 adapter contract
- `FileHandleCenter` 最小 API
- hub 入口的 ingress file preprocessing
- `files.db`
  - `file_assets`
  - `file_relations`
  - `file_notes`
- local storage layout
- retention / cleanup v1
- vision 路徑修正方向（local file + SDK attachments）

### Out of Scope

- 完整 antivirus runtime
- container / Docker containment
- shared object storage
- 多節點 deployment
- 全部既有 file-related tools 一次重寫

## Milestones

### M1. Core Contracts + DB Skeleton

建立後續重構都會依賴的核心契約與 DB 結構。

#### Work

- 定義 `SourceHandleInput`
- 定義 `SourceFetchResult`
- 定義 `CanonicalFileHandle`
- 定義 `MaterializedAsset`
- 建 `files.db`
  - `file_assets`
  - `file_relations`
  - `file_notes`
- 建 storage layout helper

#### Done When

- 型別與 schema 明確可被 adapter / center / tool 共同使用
- `files.db` 可建立與基本 CRUD
- `route_id`、`file_id`、retention/scan 欄位都齊

### M2. FileHandleCenter 最小可運作版本

建立中心服務與 policy 掛點。

#### Work

- 實作 `register`
- 實作 `download_now`
- 實作 `prefetch`
- 實作 `get_asset`
- 實作 `ensure_local`
- 建立 retention / scan status / local persistence 基礎流程

#### Done When

- 給一個 `SourceHandleInput`，可 register 成 canonical file record
- `download_now` 可透過 adapter fetch 並落地 local asset
- `ensure_local` 可穩定回傳 usable path

### M3. Ingress Integration

將外部平台 file/media 正式接進主流程。

#### Work

- 在 hub 入口新增 file ingress preprocessor
- 將 adapter parse 出來的 file/media 轉成 source handle
- 在 `hub.receive()` 最前面 register + policy
- audio route 接到 STT 前置流程

#### Done When

- inbound image/audio/file 不再靠 scattered parser 驅動後續流程
- STT 可以透過 canonical file path 取檔
- hub 不再自己維護 file-specific special logic

### M4. Vision Path Fix

把目前 broken 的 vision 路徑改成 SDK 正常可吃的模式。

#### Work

- 驗證本機 vision-capable model capability
- 做最小 POC：local image file + SDK attachments
- 改寫 batch vision / image analyze 路徑
- 將 `download_media -> binaryResultsForLlm` 從 vision 核心路徑移除

#### Done When

- Claude/Copilot vision model 能真的讀到圖片
- image analysis 不再依賴目前已確認失效的 binary tool-result transport

### M5. Tool-by-Tool Convergence

逐步把現有 scattered tool 邏輯收斂到 center。

#### Priority

1. `download_media`
2. `show_image`
3. `document_edit`
4. STT / image analyze / batch vision 相關路徑

#### Done When

- 主要 file-related tool 不再自己 parse platform ref / adapter lookup / local hardcode path
- file lineage 與 exposure 開始走同一套 DB / policy

## Implementation Strategy

### 原則

- 先立契約與中心，再做嫁接
- 先做最小通路，不一次重寫全部工具
- 先修已確認的 broken path（vision），再擴大治理面
- 需要起測試 server / 跑 E2E 前，先主動清掉現有本機 chatpilot 服務，避免 port / tunnel / webhook 干擾

### 策略

- 以 `FileHandleCenter` 為唯一 ingress gate
- adapter 保持平台翻譯器 + fetch primitive 角色
- 現有 scattered tool 先逐步接入，不急著一次替換
- 讓 DB 與 storage layout 先成形，避免後續 migration 更痛
- 先用 mock / integration 證明 center 本身正確，再沿主流程一路一路串上去
- 若某一段整合受前置進度阻塞，可先 skip，保留測試入口與待辦，不硬擠全綠

## Risks

### 1. 既有工具改寫範圍擴大

file/media 邏輯目前散在多處，收斂過程中容易牽動：

- `download_media`
- `show_image`
- `document_edit`
- hub STT
- pipeline vision

### 2. Vision POC 若受限於本機 SDK/CLI 版本

即使本地型別顯示支援 `attachments` 與 `vision` capability，
仍需實測當前可用模型與 CLI 版本是否真的可讀圖。

### 3. retention / cleanup 過早實作過深

本輪應先做可用的 default lifecycle，
避免一開始就把 retention 變成完整 archive product。

## Validation

### Unit

- DB schema / CRUD
- register / ensure_local / retention status transitions
- route partition path generation
- relation / note write-read

### Integration

- adapter source handle → register → local asset
- audio ingress → local file → STT
- image ingress → local file → vision attachment

### E2E

- user 傳圖片後，vision pipeline 能實際讀到圖
- user 傳音檔後，STT 能從 canonical local asset 運作
- session reset 後，仍能透過 route-level file memory 查到前一天 file metadata / notes

### E2E / Server 注意事項

- 進入需要 localhost:2999 測試 server 的 phase 前，先停止目前本機正在跑的 chatpilot 服務
- 原因：
  - 避免 port 衝突
  - 避免 tunnel / webhook 被既有服務占用
  - 減少測試結果被現存 runtime 狀態污染
- 雖然部分測試未必用到 LINE，但本輪仍以保守策略處理

### Current Staged Validation Status

- `FileHandleCenter` foundation、DB schema、storage layout：已由 mock / unit / integration 驗證。
- adapter ingress + hub/STT 嫁接：已由 integration tests 驗證 canonical file registration 與 audio eager download。
- file-producing / file-consuming tools：已由 targeted integration tests 驗證 `download_media`、`document_edit`、`show_image` 的 canonical lookup、lineage 與 exposure behavior。
- vision attachment path：已由 integration tests 驗證 local file attachments 可正確送入 SDK。
- 下一步 E2E：在 localhost:2999 起測試 server 前，先停止現有本機 chatpilot 服務，並優先驗證 vision / document / image response 這幾條已完成嫁接的真實場景。

## Recommended Order

1. 型別與 DB schema
2. `FileHandleCenter` 最小 API
3. storage layout helper
4. hub ingress integration
5. vision POC
6. tool convergence
