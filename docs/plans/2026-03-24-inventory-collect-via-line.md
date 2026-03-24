# LINE 盤點收集功能

> **日期：** 2026-03-24
> **狀態：** Draft
> **相關：** warehouse-batch-inventory skill、warehouse API search 同義詞改進

---

## 背景與需求

### 現況痛點

目前倉庫盤點流程：

```
iPhone 逐品項拍照 → AirDrop 到 Mac → 複製到專案目錄 → Claude Code 批次分析
```

瓶頸：
1. **一張照片只能對應一個品項** — 不清楚的不能多拍角度，整架拍一張反而更快
2. **AirDrop + 複製是手動摩擦** — 88 張照片傳輸耗時
3. **拍照過程無法附帶說明** — 語音/文字備註無法和照片對應
4. **必須全部拍完才能開始分析** — 不能邊拍邊處理

### 目標

用 LINE（chatpilot shinyipaint bot）作為拍照入口，達成：

- **免 AirDrop** — 照片直接從手機到 server
- **每張照片可附語音/文字備註** — 自然對應
- **支援多張照片描述同一品項** — 文字說明「這三張是同一桶」
- **批次上傳** — 建議 10-20 張拍完一個段落就傳
- **語音自動轉文字** — STT 後按時間順序對應照片

### 使用流程

```
用戶：「盤點 K1」
Bot ：「K1 盤點開始，請拍照上傳，10-20 張一批，拍完說『上傳』」

[收集模式 — Bot 只存不回 LLM]
用戶：傳 12 張照片
Bot ：「✓ 已收 12 張」
用戶：傳語音「接下來是角落那堆 Jikitone」
Bot ：「✓ 已收 1 段語音」
用戶：傳 8 張照片
用戶：傳文字「這三張是同一桶看不清的」
Bot ：「✓ 已收 8 張 + 1 則備註」

用戶：「上傳」
Bot ：「批次 1 歸檔完成：20 張照片 + 1 段語音 + 1 則備註
       語音轉錄：『接下來是角落那堆 Jikitone』→ 關聯照片 13-20」

[繼續下一批或結束]
用戶：「K1 結束」
Bot ：「K1 盤點 session 結束。共 2 批次、35 張照片、2 段語音。
       檔案在 inventory_sessions/20260324_K1/」
```

---

## 技術設計

### 架構概覽

```
LINE 用戶
  │
  │ 圖片/音檔/文字
  ▼
Hub (hub.py)
  │
  ├─ [收集模式 ON] → 直接存入 session buffer，輕量回覆
  │                   不走 LLM（省時省錢）
  │
  └─ [收集模式 OFF / 指令訊息] → 正常 LLM 流程
                                    │
                                    ▼
                              inventory_session tool  (start/end/status)
                              inventory_collect tool  (下載/歸檔/STT)
```

### 收集模式設計

核心概念：在 Hub 層攔截，**收集模式中的媒體訊息不走 LLM**。

```python
# hub/hub.py 新增
class InventorySession:
    conversation_id: str
    unit_id: str
    started_at: datetime
    batches: list[SessionBatch]
    current_batch: SessionBatch

class SessionBatch:
    media_refs: list[MediaRef]  # {type: "image"|"audio", ref: "line:{msg_id}", timestamp}
    text_notes: list[TextNote]  # {text: str, timestamp: datetime}
```

判斷邏輯：
```python
async def receive(self, message, adapter):
    session = self._inventory_sessions.get(message.conversation_id)
    if session and message.has_media:
        # 收集模式：存 ref，輕量回覆
        session.current_batch.add(message)
        await adapter.send_reply(message, f"✓ 已收 {session.current_batch.photo_count} 張")
        return
    # 文字訊息檢查是否為「上傳」「結束」等關鍵字
    if session and self._is_collect_command(message.text):
        # 走 LLM 處理指令
        pass
    # 正常流程
    ...
```

### LINE Parser 音檔支援

現況：parser.py 處理 text、image、file，**缺 audio**。

新增：
```python
# adapters/line/parser.py
elif event.message.type == "audio":
    media_ref = f"line:{event.message.id}"
    text = f"[音檔 ref:{media_ref}]"
    # duration_ms = event.message.duration (可用於時間對齊)
```

### Tools

#### inventory_session

```python
# tools/builtin/inventory_session.py
name: "inventory_session"
description: "管理倉庫盤點 session。action: start/end/status"
parameters:
  action: "start" | "end" | "status"
  unit_id: str (start 時必填)

# start → 在 hub 設定收集模式，回傳 session_id
# end   → 關閉收集模式，回傳 session 摘要
# status → 回傳目前收集進度
```

#### inventory_collect

```python
# tools/builtin/inventory_collect.py
name: "inventory_collect"
description: "將當前批次的照片/語音下載歸檔並轉錄語音"
parameters:
  session_id: str

# 流程：
# 1. 讀 session buffer 中所有 media refs
# 2. 批次呼叫 adapter.download_media() 下載照片 + 音檔
# 3. 音檔 → OpenAI Whisper API → transcript
# 4. 按 timestamp 順序配對：文字/語音 ↔ 前後照片
# 5. 存到 data/inventory_sessions/{date}_{unit}/
# 6. 回傳摘要 JSON
```

### STT 整合

參考 `stt-transcribe` skill，使用 OpenAI Whisper API：

```python
async def transcribe_audio(audio_bytes: bytes, filename: str) -> dict:
    """Call OpenAI Whisper API for transcription."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://api.openai.com/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            files={"file": (filename, audio_bytes, "audio/m4a")},
            data={"model": "whisper-1", "language": "zh", "response_format": "verbose_json"},
        )
    return resp.json()  # {text, language, duration, segments[]}
```

### 文字/語音 ↔ 照片關聯

用 LINE message timestamp 排序：

```
t=10:01:00  IMG_001.jpg
t=10:01:02  IMG_002.jpg
t=10:01:05  [音檔] "這幾桶是得利特白"     → 關聯 IMG_001, IMG_002
t=10:01:10  IMG_003.jpg
t=10:01:15  IMG_004.jpg
t=10:01:16  IMG_005.jpg
t=10:01:20  [文字] "這三張是同一桶"         → 關聯 IMG_003, IMG_004, IMG_005
```

規則：
- 語音/文字 **往前關聯** 到最近一組連續照片（直到上一個語音/文字為止）
- 寫入 session.json 的 `annotations` 欄位

### 歸檔結構

```
data/inventory_sessions/
  20260324_K1/
    batch_001/
      photos/
        001.jpg
        002.jpg
        ...
      audio/
        001.m4a
    batch_002/
      ...
    session.json
```

`session.json` 格式：
```json
{
  "unit_id": "K1",
  "date": "2026-03-24",
  "started_at": "2026-03-24T10:00:00",
  "ended_at": "2026-03-24T10:30:00",
  "batches": [
    {
      "batch_id": "001",
      "photos": [
        {"file": "batch_001/photos/001.jpg", "timestamp": "2026-03-24T10:01:00"},
        {"file": "batch_001/photos/002.jpg", "timestamp": "2026-03-24T10:01:02"}
      ],
      "annotations": [
        {
          "type": "voice",
          "file": "batch_001/audio/001.m4a",
          "transcript": "這幾桶是得利特白",
          "timestamp": "2026-03-24T10:01:05",
          "related_photos": ["batch_001/photos/001.jpg", "batch_001/photos/002.jpg"]
        }
      ]
    }
  ],
  "summary": {
    "total_photos": 35,
    "total_voice": 2,
    "total_text_notes": 3
  }
}
```

---

## 改動範圍

| 檔案 | 動作 | 說明 |
|------|------|------|
| `adapters/line/parser.py` | 修改 | 加 audio message 解析 |
| `hub/hub.py` | 修改 | 加收集模式 state machine + buffer |
| `tools/builtin/inventory_session.py` | **新增** | start/end/status session 管理 |
| `tools/builtin/inventory_collect.py` | **新增** | 批次下載 + 歸檔 + STT + 關聯 |
| `config/routes.yaml` | 修改 | shinyipaint tools 加 inventory_session, inventory_collect |
| `server/__init__.py` | 修改 | 註冊兩個新 tool |

### 依賴

- `httpx` — 已有（async HTTP for Whisper API）
- `OPENAI_API_KEY` — 環境變數或 config（stt-transcribe 用的同一把）

---

## 實作順序

### Phase 1: 收集管線（讓流程通）

1. LINE parser 加 audio
2. Hub 收集模式 state machine
3. inventory_session tool (start/end)
4. 基本歸檔（照片下載存檔，音檔先存不轉錄）

### Phase 2: STT + 關聯

5. inventory_collect tool 加 Whisper STT
6. 時間戳排序 + 語音/文字 ↔ 照片自動關聯
7. session.json 輸出

### Phase 3: 接分析（後續）

8. session.json 作為 warehouse-batch-inventory skill 的 input
9. Agent team 自動觸發分析（或手動觸發）

---

## 備註

- 此功能的分析端（辨識油漆品項 + 比對 DB + 寫入）已在 warehouse-batch-inventory skill 中實作完成（2026-03-23 K1 盤點驗證過）
- warehouse API search 已加入同義詞擴展（消光↔平光、黑色↔黑 等），同日完成
- 收集模式不走 LLM 是關鍵設計：20 張照片不應觸發 20 次 GPT-4 推理
