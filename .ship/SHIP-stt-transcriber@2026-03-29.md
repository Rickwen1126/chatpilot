# SHIP: STT Transcriber

tags: [ship, chatpilot, stt, audio, whisper]

## Relations
- 前置：LINE parser 已支援 AudioMessageContent（commit ba44e8d）
- 前置：download_media 已驗證可下載 LINE 語音（66KB m4a）

## 1. Problem Statement
**問題**：LINE 使用者發語音訊息時，chatbot 完全忽略（parser 以前沒處理 AudioMessageContent，現已修復但轉錄尚未實作）
**對象**：信益油漆員工（常在現場用語音而非打字）
**成功條件**：使用者在 LINE 發語音 → chatbot 能理解內容並回覆，跟打字一樣的體驗

## 2. Solution Space
| 做法 | 優勢 | 風險/代價 |
|------|------|-----------|
| A: Hub 層 STT Transcriber（方案 C 混合） | 通用、adapter 無關、私訊同步/群組異步 | 需處理轉錄時間 vs reply token 競爭 |
| B: Tool 層（chatbot 自己呼叫 transcribe tool） | 最簡單、LLM 自主決定何時轉錄 | LLM 不一定會呼叫、增加 token 消耗、每次都多一輪 tool call |
| C: Adapter 層（LINE adapter 內部轉錄） | 最快，不碰 Hub | 不通用、其他 adapter 重複實作 |

**選擇**：A — Hub 層 STT Transcriber
**原因**：通用（未來 Telegram/其他平台也用）、控制權在 Hub（可決定同步/異步）、chatbot 不需要知道有語音這回事

## 3. 技術決策清單
| 決策點 | 選擇 | 原因 | 備選 |
|--------|------|------|------|
| STT API | OpenAI gpt-4o-mini-transcribe（alias 指向最新版） | 有標點、品質好、中文佳���LINE m4a 直吃 | whisper-1（無標點）、gpt-4o-transcribe（帳號無權限） |
| 音檔格式 | m4a (LINE 原生) 直送 | Whisper 支援 m4a，不需轉檔 | 先轉 wav/mp3 |
| 私訊處理 | 同步（阻塞等轉錄完再送 chatbot） | 用戶在等回覆，UX 最直覺 | 異步 + 先回「收到語音，轉錄中…」 |
| 群組處理 | 異步入 context buffer | 跟圖片同邏輯，下次 @mention drain | 同步（但群組語音不一定要觸發回覆） |
| 轉錄結果格式 | `[音檔 ref:line:{id}]（轉錄：{文字}）` | 保留原始 ref，萬一轉錄有誤可追溯 | 直接替換為純文字 |
| 元件位置 | `src/chatpilot/stt/transcriber.py` | Hub 層獨立 class | 放 tools/ 或 hub/ 下 |

## 4. 橫向掃描
| 參考 | 值得借鏡 | 要避開的坑 |
|------|----------|-----------|
| stt-transcribe skill | Whisper API 呼叫方式、chunk 處理 | skill 是 CLI 用的，chatbot 需要 async |
| hub 圖片 context buffer | 純媒體不觸發 chatbot、等下一則文字 drain | 語音私訊不能用同邏輯（沒有下一則來 drain） |

## 5. 知識風險標記

### [B]lock
（無。技術路徑已驗證 — download 通、Whisper API 熟悉、Hub 架構清楚）

### [R]isky
- Whisper API 對 LINE m4a 的相容性：LINE 語音是 AAC-LC in m4a container，Whisper 官方支援 m4a 但沒有明確說 LINE 的 codec profile
  - Exit Questions:
    1. 把剛才下載的 66KB m4a 直接送 Whisper API 能不能轉成功？ [B — spike 驗證]
- reply token 時間預算：下載(1s) + 轉錄(2-5s) + LLM(5-15s) = 8-21s，LINE 限 30s
  - Exit Questions:
    1. 實測全程耗時多少？超過 25s 的 fallback 機制現在有效嗎？ [A]

### Spike 計畫
- Spike 1: Whisper m4a 驗證 → 覆蓋 R1 Q1
  - 做什麼：把 `/tmp/test_audio.m4a`（從 LINE 下載的那份）直接送 Whisper API
  - 預計時間：5 min

### [N]ice-to-know
- Whisper 多語言 auto-detect（應該自動偵測中文）
- 大檔案 chunk 切分（LINE 語音通常 < 5min，不需要 chunk）

## 6. 開工決策
- [x] 所有 [B]lock 已解除（無 B）
- [x] [B]lock ≤ 3 個
- [x] Problem Statement 清晰
- [x] Solution Space 有比較過
- [x] 技術決策都有根據
- [x] Spike 1 完成（gpt-4o-mini-transcribe + LINE m4a = OK，有標點、< 3s）

**狀態**：可開工
