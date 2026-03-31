# File External Memory 原則

## 結論

ChatPilot 的 file system 不應只是「把檔案存下來」。

更重要的是：

- 讓 file 先被有序化
- 讓它成為可檢索、可關聯、可片段提取的 external memory unit
- 讓不同 agent / tool / pipeline 可以透過共享的結構化 context 協作

這不是單純的附件管理，而是多代理人協作的 context substrate。

## 為什麼這件事重要

如果檔案只是散落在 local workpath：

- 命名不一致
- 沒有 route scope
- 沒有時間資訊
- 沒有 lineage
- 不知道誰建立、誰修改、誰還在用

那即使有 `rg`、有 local path、甚至有很多原始檔，
對 agent 來說仍然很難在有限 context 內有效利用。

這種狀況下，檔案只是雜亂副作用，不是可用記憶。

## 真正要做的是有序化

file 一旦先被有序化，系統可以開始支持這些能力：

- route-scoped file history
- 依時間查找先前檔案
- 依 message / task / pipeline / tool 關聯查找檔案
- 依 derived artifact 追溯來源
- 在 session reset 後仍能延續檔案脈絡，而不是一律要求重傳

例如：

- 「昨天我傳群組的照片效果如何？」
- 「上週那份 Excel 幫我補欄位」
- 「你之前幫我轉錄的音檔，再整理成會議重點」

這些都不是 session continuation，
而是 external memory 有序落地後的自然能力。

## 對 agent 協作的意義

當 file external memory 被治理過後，
跨 agent 的交接不必依賴顯式傳話或把整段歷史塞進 prompt。

真正被共享的是：

- file identity
- route ownership
- message / task / tool / pipeline relations
- derived artifacts
- summaries / transcripts / previews
- 是否仍可 re-materialize

這會讓多代理人協作看起來像「無聲默契」，
但其實是 ChatPilot 在背後提供共享的 context substrate。

## 原則

### 1. File 是 external memory unit，不只是附件

系統不應只記得「有這個檔案」，
而應記得：

- 它從哪來
- 屬於哪條 route
- 與哪些事件相關
- 現在是否仍可用

### 2. 有序化比保存本身更重要

只是存著不夠。

真正有價值的是：

- 可檢索
- 可關聯
- 可局部提取

### 3. Context 的共享比 prompt 的共享更重要

長期方向不是讓每個 agent 自己記得一切，
而是讓它們共享一個被治理好的外部 context system。

### 4. Local workpath 不是主要協作模型

裸 path / tmp file 對開發者可以勉強使用，
但不適合作為一般使用者與 agent 的主要協作模型。

正式系統應優先暴露：

- file identity
- lineage
- route / task / tool 關聯
- exposure policy

而不是散亂 path。

## 對目前設計的直接意義

這些原則支持以下方向：

- `FileHandleCenter` 作為正式 file ingress / governance boundary
- `files.db` 作為 file memory index
- `file_relations` 承接複雜關聯，而不是一直按 type 拆表
- route-scoped storage 與 lifecycle policy

## 一句話原則

**ChatPilot 的長期方向，不是讓每個 agent 自己記得所有檔案，而是讓它們共享一個被治理好的 file external memory system。**
