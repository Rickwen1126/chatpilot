# FileHandleCenter Spec

## Summary

`FileHandleCenter` 是 ChatPilot 的正式 file ingress / governance boundary。

它不只是處理外部平台下載，也應承接：

- adapter 帶進來的 file/media
- tool 產生的檔案
- pipeline / agent 產生的衍生檔
- CLI import

目標不是「把檔案存下來」而已，而是讓 file 先被有序化，成為：

- 可檢索
- 可關聯
- 可片段提取
- 可被跨 agent / 跨 session 共享的 external memory unit

## Problem

目前 repo 的 file/media 處理有幾個明顯問題：

1. ref/parser 分散在多處
   - `src/chatpilot/adapters/line/parser.py`
   - `src/chatpilot/tools/builtin/download_media.py`
   - `src/chatpilot/tools/builtin/show_image.py`
   - `src/chatpilot/tools/builtin/document_edit.py`
   - `src/chatpilot/hub/hub.py`
2. file/media lifecycle 沒有單一真相
3. tool 可以各自 hardcode local file / parse ref / upload / expose
4. 原始檔、衍生檔、route scope、lineage 沒有正式索引
5. 目前 vision 路徑已確認有結構性 bug
   - repo 目前依賴 `download_media -> binaryResultsForLlm`
   - 但本機 Python Copilot SDK transport 並不會把 `binary_results_for_llm` 傳進模型
   - 正確方向應改成 local file + SDK `attachments=[{"type":"file","path":"..."}]`

## Goals

- 建立單一 file ingress 入口
- 建立穩定的 canonical file identity
- 讓 route 成為 file ownership / partition 的一等公民
- 讓 eager / lazy / background download 變成 policy，而不是 scattered logic
- 建立 file memory index，支援 session reset 後的 route-level file recall
- 為未來 tool / pipeline / agent generated files 留出正式治理邊界

## User Stories

- 作為一般使用者，我希望在 session 重置後仍可問「昨天我傳群組的照片效果如何」，而系統能基於 route-level file memory 回答，不是只會要求我重傳。
- 作為使用者，我希望私訊 bot 請它整理我上傳的 Excel 時，系統能有秩序地納管原檔、衍生檔與後續摘要，而不是讓 agent 亂丟 workpath。
- 作為 vision / STT 類 workflow 的使用者，我希望圖片、音檔與文件一進系統就能被正確 register 並按 policy 預抓，避免後續流程各自用 ad-hoc parser 重做一次。
- 作為工具與 pipeline 開發者，我希望 file ingress、下載、local path 取得與暴露都走同一套 center，不需要在每個 tool 裡重寫 adapter lookup、ref parse 與 local file hardcode。
- 作為未來的多代理人協作者，我希望不同 agent 能透過被治理過的 external file memory 無聲交接，而不是靠完整 prompt 歷史或隨機 path 猜測脈絡。

## Non-Goals

- 本輪不做完整 antivirus / container hardening
- 本輪不做多 backend object storage 抽象
- 本輪不做 source/materialized/derived 的完全正規化多表設計
- 本輪不做所有現有 file-related tools 的全面重寫，但設計必須能承接後續重構

## Validation Notes

- 本 feature 採 staged rollout：先證明 center 本體與 DB/schema 正確，再逐段嫁接到 adapter、hub、tool、pipeline。
- 已完成的嫁接路徑，必須優先補 targeted integration / E2E；不可用「功能還沒全部做完」當作忽略失敗的理由。
- 目前已完成並測過的高價值路徑包括：audio ingress/STT、canonical file recall、generated file governance、vision local attachment、以及 `download_media` / `document_edit` / `show_image` 的 canonical file path。
- 自動化 E2E 已新增 file-center 行為驗證：
  - mock image ingress → canonical file row register-only
  - mock audio ingress → policy `download_now` → local asset materialized
  - 驗證層級包含 log、`files.db`、以及 local asset path existence
- 真正需要 localhost:2999 與 tunnel/webhook 的 E2E 階段，必須先停止現有本機 chatpilot 服務，避免 runtime state 與 port 干擾。

## Architecture

### Adapter Responsibility

adapter 是平台邊界。

它的責任是：

- 把平台原生 file/media event 翻成 `SourceHandleInput`
- 根據 `SourceHandleInput` 回平台抓回檔案 bytes

它不負責：

- 分配 `file_id`
- 決定 eager / lazy / background
- local file persistence
- retention / scan / exposure policy

### FileHandleCenter Responsibility

`FileHandleCenter` 是系統內 file handling service。

它的責任是：

- canonicalization
- 分配 `file_id`
- register ingress
- 執行 policy
- orchestration blocking/background download
- local materialization
- 管理 file index / relations / notes
- 提供後續暴露與取用入口

### Tool / Agent Responsibility

tool / agent 不直接處理平台差異。

它們應：

- 只透過 `FileHandleCenter` 取得 canonical handle / asset / local path
- 不直接 hardcode local file path
- 不自己 parse platform ref

## Core Models

### SourceHandleInput

adapter 交給系統的來源檔案描述。

建議欄位：

- `route_id`
- `platform`
- `kind`
- `native_locator`
- `filename?`
- `mime_type?`
- `platform_context`

#### Native Locator v1

- `native_locator` v1 先用 `str`
- 這是刻意的 YAGNI
- 若未來第二個平台真的需要複合 locator，再升級 schema

### CanonicalFileHandle

系統內對 file unit 的 canonical identity。

建議欄位：

- `file_id`
- `route_id`
- `platform`
- `native_locator`
- `kind`
- `filename?`
- `mime_type?`
- `platform_context`

#### Primary Key

- `file_id` 使用 opaque UUID
- `file_id` 是真正 primary key
- `file_id` 由 `FileHandleCenter.register(...)` 分配
- adapter 不分配 internal id

### SourceFetchResult

adapter 平台抓取後回給中心的結果。

建議欄位：

- `data: bytes`
- `filename?`
- `mime_type?`
- `size_bytes?`

### MaterializedAsset

代表已下載 / 已落地 / 已可供後續使用的 asset 狀態。

它不是 source identity。

至少應涵蓋：

- `file_id`
- `storage_backend`
- `local_path?`
- `public_url?`
- `sha256?`
- `size_bytes?`
- `scan_status`
- `materialized_at`
- `expires_at`

## Ingress Flow

### 原則

- 所有 file ingress 都必須先進 `register(...)`
- 預下載不由 adapter side-channel 觸發
- eager / lazy / background 由 policy 決定

### 掛點

ingress file preprocessing 應放在：

- `hub.receive()` 最前面
- 在 STT / routing / mention filter 之前

但實作上應抽成獨立 service，不把 file orchestration 塞進 hub 本體。

### 流程

1. adapter parse 出 `Message`
2. adapter 提供 `SourceHandleInput`
3. ingress preprocessor 呼叫 `FileHandleCenter.register(...)`
4. center 分配 `file_id`
5. policy 決定：
   - 只 register
   - `download_now`
   - `prefetch`
6. message 再繼續進 hub / chatbot / pipeline

## Public API

v1 最小 public API：

- `register(source) -> CanonicalFileHandle`
- `download_now(file_id) -> MaterializedAsset`
- `prefetch(file_id) -> None | task_id`
- `get_asset(file_id) -> MaterializedAsset | None`
- `ensure_local(file_id) -> str`

### Naming

- 文件概念上可以使用 materialization
- 但 API 名稱優先偏直覺：
  - `download_now`
  - `prefetch`
  - `ensure_local`

### Read Bytes

- `read_bytes` 先不做一等 public API
- bytes 能力作為內部 primitive 保留
- 目前更重要的是 `ensure_local`
  - 尤其 vision 路徑要走 SDK `attachments`

## DB Design

### file_assets

v1 使用單表承接 file unit 本體與當前 materialized state。

建議欄位：

- `file_id`
- `route_id`
- `source_platform`
- `source_native_locator`
- `source_kind`
- `source_filename`
- `source_mime_type`
- `source_platform_context_json`
- `fetch_status`
- `storage_backend`
- `local_path`
- `public_url`
- `sha256`
- `size_bytes`
- `scan_status`
- `created_at`
- `materialized_at`
- `last_accessed_at`
- `expires_at`
- `is_pinned`
- `retention_class`

### file_relations

複雜度優先走 relation，不按 type 拆表。

建議極簡 schema：

- `relation_id`
- `from_file_id`
- `relation_type`
- `to_file_id?`
- `subject_type?`
- `subject_id?`
- `metadata_json`
- `created_at`

適用於：

- `derived_from`
- `generated_by_tool`
- `generated_by_pipeline`
- `attached_to_message`
- `imported_from_cli`
- `shown_in_response`

### file_notes

用來保留代理人的分析、摘要與註解，讓原始檔回收後仍保有回答脈絡。

建議欄位：

- `note_id`
- `file_id`
- `note_type`
- `content`
- `metadata_json`
- `created_at`
- `created_by`

可能的 `note_type`：

- `summary`
- `analysis`
- `caption`
- `ocr`
- `transcript`
- `annotation`

## Storage Layout

local layout v1：

```text
data/file_assets/
  {route_partition}/
    {file_id}/
      source.bin
      meta.json
      derived/
```

原則：

- 以 `route_id` 做 partition
- 以 `file_id` 做 file unit 目錄
- local path 穩定性優先於原始檔名可讀性
- `meta.json` 可保留 debug / recovery metadata，但 DB 仍是 source of truth

## Retention / Cleanup

### 基本欄位

- `expires_at`
- `retention_class`
- `is_pinned`

### v1 Default

- `retention_class = default`
- `default = 7 days`

### Policy

- cleanup 先刪 asset，不刪記憶
- 原始檔可過期
- metadata / relations / notes 可長期保留
- 每次成功使用更新 `last_accessed_at`
- `is_pinned` 可覆蓋 cleanup

## Scan / Exposure

### v1 原則

- 要有 `scan_status`
- 要有 gate points
- 但不急著上重型掃描器

建議最少狀態：

- `unscanned`
- `clean`
- `suspicious`
- `failed`

### Exposure Policy

安全判斷不只看掃毒，也看：

- file origin
- relation lineage
- route scope

像 `show_image` 這類主動回推給使用者的行為，
應依 file origin + relation lineage + route scope 決定是否可暴露。

## Vision Integration

### 已確認問題

目前 repo 的 vision 路徑依賴：

- 純文字 `[圖片 ref:...]`
- `download_media`
- `ToolResult.binaryResultsForLlm`

但本機 Python Copilot SDK transport 不會把 `binary_results_for_llm` 傳到模型。

### 正確方向

- 先用 `FileHandleCenter` 將圖片 materialize 成 local file
- 再透過 SDK `attachments=[{"type":"file","path":"..."}]` 將圖片送進 model

這會直接影響：

- batch vision
- image analyze
- 任何需要模型直接看圖的路徑

## External Memory Direction

長期來看，file 不只是附件，而是 route-scoped external memory。

做對之後，系統可以支持：

- session reset 後仍可依 route 查昨天的圖片 / 文件 / 音檔
- 跨 agent 共享被治理過的 file context
- 不靠 workpath 雜亂檔名與 ad-hoc path 傳遞脈絡

這是未來方向，但本輪實作仍以最小落地為準。

## Out-of-Scope Follow-Ups

以下議題已確認重要，但不納入本輪：

- system security boundary / agent containment
- 更強的 execution isolation
  - 例如高風險 async mission 丟進 container / Docker
- 完整 antivirus / quarantine runtime
- shared object storage / multi-node deployment

## Implementation Priority

1. 定 `SourceHandleInput` / `SourceFetchResult`
2. 定 adapter fetch contract
3. 在 hub 入口掛 ingress file preprocessor
4. 實作 `FileHandleCenter` 最小 API
5. 建 `files.db`
   - `file_assets`
   - `file_relations`
   - `file_notes`
6. 建 local storage layout
7. 改寫 vision path
   - local file + SDK attachments
8. 再逐步收斂 `download_media` / `show_image` / `document_edit`

## Related Notes

- `docs/reference/file-handle-center-design.md`
- `docs/reference/file-external-memory-principles.md`
- `docs/todo/20260331.md`
- `docs/file-handle-center/plan.md`
