# 信益油漆 Tools Spec: 報價協助 & 日常文件修改

為 chatpilot 新增兩個信益油漆業務工具：報價歷史搜尋與文件編輯。

---

## Tool 1: quote_search（報價協助）

### 使用情境

業主來電需要油漆報價，員工在 LINE 群組請 bot 查詢過去類似案件的報價紀錄，bot 搜尋歷史資料後整理成比較報告回傳。

**典型對話**：
```
員工：「幫我找過去類似住宅建案的報價紀錄，大概 500 坪左右」
Bot：搜尋歷史報價 → 整理比較報告 → 回傳
```

### Tool 定義

```python
ToolDefinition(
    name="quote_search",
    description=(
        "搜尋信益油漆歷史報價紀錄。"
        "可依建案類型（住宅/商辦/廠房）、坪數範圍、油漆品牌篩選。"
        "回傳匹配的歷史報價資料，供整理比較報告。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "keyword": {
                "type": "string",
                "description": "搜尋關鍵字（案名、品牌、備註等）",
            },
            "building_type": {
                "type": "string",
                "enum": ["住宅", "商辦", "廠房"],
                "description": "建案類型篩選",
            },
            "min_area": {
                "type": "number",
                "description": "最小坪數",
            },
            "max_area": {
                "type": "number",
                "description": "最大坪數",
            },
            "brand": {
                "type": "string",
                "description": "油漆品牌篩選（如：虹牌、立邦、得利）",
            },
        },
        "required": [],
    },
    handler=handler,
    access_level=AccessLevel.GLOBAL,
)
```

### 資料模型

每筆報價紀錄欄位：

| 欄位 | 型別 | 說明 |
|------|------|------|
| `id` | `str` | 報價編號 |
| `project_name` | `str` | 案名 |
| `date` | `str` | 報價日期（YYYY-MM-DD） |
| `building_type` | `str` | 建案類型（住宅/商辦/廠房） |
| `area_ping` | `int` | 坪數 |
| `paint_brand` | `str` | 油漆品牌 |
| `paint_type` | `str` | 油漆種類（水泥漆/乳膠漆/防水漆等） |
| `paint_volume_liters` | `int` | 用量（公升） |
| `total_amount` | `int` | 總金額（新台幣） |
| `notes` | `str` | 備註 |

### 模擬資料

MVP 階段用 JSON 檔案儲存於 `data/quotes/quotes.json`：

```json
[
  {
    "id": "Q-2025-001",
    "project_name": "幸福社區 A 棟",
    "date": "2025-06-15",
    "building_type": "住宅",
    "area_ping": 500,
    "paint_brand": "虹牌",
    "paint_type": "水泥漆",
    "paint_volume_liters": 800,
    "total_amount": 150000,
    "notes": "含外牆防水底漆"
  },
  {
    "id": "Q-2025-002",
    "project_name": "科技園區辦公大樓",
    "date": "2025-08-20",
    "building_type": "商辦",
    "area_ping": 2000,
    "paint_brand": "立邦",
    "paint_type": "乳膠漆",
    "paint_volume_liters": 3200,
    "total_amount": 800000,
    "notes": "室內全棟，含天花板"
  },
  {
    "id": "Q-2025-003",
    "project_name": "大安花園住宅",
    "date": "2025-09-10",
    "building_type": "住宅",
    "area_ping": 350,
    "paint_brand": "得利",
    "paint_type": "乳膠漆",
    "paint_volume_liters": 560,
    "total_amount": 180000,
    "notes": "高級住宅，色彩客製"
  },
  {
    "id": "Q-2025-004",
    "project_name": "中和工業廠房",
    "date": "2025-10-05",
    "building_type": "廠房",
    "area_ping": 3000,
    "paint_brand": "虹牌",
    "paint_type": "防水漆",
    "paint_volume_liters": 5000,
    "total_amount": 450000,
    "notes": "地坪 + 牆面防水"
  },
  {
    "id": "Q-2025-005",
    "project_name": "信義商辦 B 棟",
    "date": "2025-11-12",
    "building_type": "商辦",
    "area_ping": 1200,
    "paint_brand": "立邦",
    "paint_type": "乳膠漆",
    "paint_volume_liters": 1900,
    "total_amount": 520000,
    "notes": "辦公區 + 公共空間"
  },
  {
    "id": "Q-2026-001",
    "project_name": "新莊幸福城",
    "date": "2026-01-08",
    "building_type": "住宅",
    "area_ping": 800,
    "paint_brand": "虹牌",
    "paint_type": "水泥漆",
    "paint_volume_liters": 1300,
    "total_amount": 230000,
    "notes": "社區大樓三棟"
  },
  {
    "id": "Q-2026-002",
    "project_name": "桃園物流中心",
    "date": "2026-02-14",
    "building_type": "廠房",
    "area_ping": 5000,
    "paint_brand": "虹牌",
    "paint_type": "環氧地坪漆",
    "paint_volume_liters": 8000,
    "total_amount": 950000,
    "notes": "倉儲地坪，抗壓耐磨"
  },
  {
    "id": "Q-2026-003",
    "project_name": "板橋馥華社區",
    "date": "2026-03-01",
    "building_type": "住宅",
    "area_ping": 600,
    "paint_brand": "得利",
    "paint_type": "乳膠漆",
    "paint_volume_liters": 960,
    "total_amount": 280000,
    "notes": "全室內，含兒童房低 VOC 漆"
  }
]
```

### 搜尋邏輯

篩選條件為 AND 關係，所有參數皆可選：

| 參數 | 篩選方式 |
|------|----------|
| `keyword` | 模糊比對 `project_name`、`paint_type`、`notes` |
| `building_type` | 完全匹配 |
| `min_area` / `max_area` | 範圍篩選 `area_ping` |
| `brand` | 模糊比對 `paint_brand` |

無任何參數時回傳全部資料（最近 10 筆）。

### 回覆格式

LLM 拿到搜尋結果後自行整理比較報告，tool 回傳原始 JSON 資料。報告範例：

```
找到 3 筆類似住宅建案報價：

1. 幸福社區 A 棟（2025-06）
   500坪 / 虹牌水泥漆 / 800L / $150,000
   📝 含外牆防水底漆

2. 大安花園住宅（2025-09）
   350坪 / 得利乳膠漆 / 560L / $180,000
   📝 高級住宅，色彩客製

3. 新莊幸福城（2026-01）
   800坪 / 虹牌水泥漆 / 1,300L / $230,000
   📝 社區大樓三棟

💡 參考單價：$288~$514/坪（依品牌和漆種差異大）
```

### 實作位置

`src/chatpilot/tools/builtin/quote_search.py`

### 後續擴展

- JSON → SQLite（資料量增長後）
- 新增報價建立功能（目前僅查詢）
- 接入正式 ERP 報價系統

---

## Tool 2: document_edit（日常文件修改）

### 使用情境

員工上傳 Excel 或 Word 檔案，請 bot 幫忙修改內容，bot 處理完後上傳到 R2 並回傳下載連結。

**典型對話**：
```
員工：[上傳 Excel] 幫我把這個月的出貨統計加上去
Bot：下載檔案 → 用 openpyxl 追加資料 → 上傳 R2 → 回傳下載連結

員工：[上傳 Word] 幫我在最後加上總結段落
Bot：下載檔案 → 用 python-docx 加段落 → 上傳 R2 → 回傳下載連結
```

### LINE 檔案接收流程

LINE 傳送檔案等同 `FileMessageContent`，與圖片相同透過 message ID + Get Content API 下載。

Parser 處理方式：
```
[檔案 ref:line:{message_id}:{filename}]
```
存入 context buffer，tool 透過 `download_media` 取得檔案 bytes。

### Tool 定義

```python
ToolDefinition(
    name="document_edit",
    description=(
        "編輯 .docx 或 .xlsx 檔案。"
        "接收檔案參考 ref 和編輯指令，處理後上傳並回傳下載連結。"
        "支援操作：追加工作表列、新增段落、修改內容等。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "file_ref": {
                "type": "string",
                "description": "檔案參考 ID（如 line:msg_123:report.xlsx）",
            },
            "instruction": {
                "type": "string",
                "description": "編輯指令（如：在最後加上總結段落、追加一列出貨資料）",
            },
            "data": {
                "type": "string",
                "description": "需要寫入的具體資料（JSON 格式），如追加的表格列內容",
            },
        },
        "required": ["file_ref", "instruction"],
    },
    handler=handler,
    access_level=AccessLevel.GLOBAL,
)
```

### 執行流程

```
1. 解析 file_ref → 取得 platform, message_id, filename
2. 呼叫 adapter.download_media(message_id) 下載檔案 bytes
3. 判斷副檔名 → 選擇處理器
   - .xlsx → openpyxl
   - .docx → python-docx
   - 其他 → 回傳不支援格式錯誤
4. 根據 instruction + data 執行編輯
5. 將結果 bytes 上傳 R2（chatpilot.storage.r2）
6. 回傳公開 URL 給 LLM
7. LLM 組織回覆，附下載連結告知使用者
```

### 支援操作

#### .xlsx（openpyxl）

| 操作 | 說明 |
|------|------|
| `append_rows` | 在現有工作表末尾追加列 |
| `add_sheet` | 新增工作表並填入資料 |
| `update_cells` | 更新指定儲存格內容 |

#### .docx（python-docx）

| 操作 | 說明 |
|------|------|
| `append_paragraph` | 在文件末尾追加段落 |
| `append_table` | 追加表格 |
| `replace_text` | 全文搜尋取代 |

### R2 上傳

複用 `chatpilot.storage.r2.R2Storage`：

```python
r2 = R2Storage()

# .xlsx
url = await r2.upload(
    data=output_bytes,
    content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    extension="xlsx",
)

# .docx
url = await r2.upload(
    data=output_bytes,
    content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    extension="docx",
)
```

### 回覆格式

```
已完成修改！

📄 下載連結：https://media.chatpilot.example.com/abc123.xlsx
（連結 7 天內有效）

修改內容：在「出貨統計」工作表追加了 3 月份的 5 筆出貨紀錄。
```

### 錯誤處理

| 情境 | 處理方式 |
|------|----------|
| 不支援的檔案格式 | 回傳 `目前只支援 .docx 和 .xlsx 格式` |
| 檔案下載失敗 / 過期 | 回傳 `無法下載檔案，可能已過期，請重新上傳` |
| 檔案損壞無法解析 | 回傳 `檔案格式異常，無法開啟` |
| R2 上傳失敗 | 回傳 `檔案處理完成但上傳失敗，請稍後再試` |
| 檔案超過 10MB | 回傳 `檔案過大（超過 10MB），請縮小檔案後再試` |

### 實作位置

`src/chatpilot/tools/builtin/document_edit.py`

### 新增依賴

```toml
# pyproject.toml
[project.optional-dependencies]
docs = [
    "python-docx>=1.1",
    "openpyxl>=3.1",
]
```

或直接加入主要依賴（如果所有部署都需要）：

```toml
dependencies = [
    # ... existing ...
    "python-docx>=1.1",
    "openpyxl>=3.1",
]
```

### 限制與注意事項

- LINE 檔案最大 200MB，但實際上傳通常 < 10MB；tool 設 10MB 硬限制
- `download_media` 已存在可直接複用，file ref 格式需擴展支援 `platform:message_id:filename` 三段式
- 編輯操作由 LLM 根據使用者指令決定，tool 只負責執行結構化的編輯動作
- R2 storage 已可用（`chatpilot.storage.r2.R2Storage`）
- 不支援 .pdf 編輯（僅 .docx / .xlsx）

---

## Chatbot Config 變更

在 `config/routes.yaml` 對應的 chatbot 設定中加入新 tool：

```yaml
chatbots:
  shinyipaint:
    model: gpt-4o
    system_message: |
      你是信益油漆的 AI 助手。
      ...
    tools:
      - warehouse_query
      - quote_search      # 新增
      - document_edit      # 新增
      - download_media
      - web_search
```

## 檔案清單

| 檔案 | 動作 | 說明 |
|------|------|------|
| `src/chatpilot/tools/builtin/quote_search.py` | 新增 | quote_search tool 實作 |
| `src/chatpilot/tools/builtin/document_edit.py` | 新增 | document_edit tool 實作 |
| `data/quotes/quotes.json` | 新增 | 模擬報價資料 |
| `src/chatpilot/tools/registry.py` | 修改 | 註冊新 tool |
| `config/routes.yaml` | 修改 | chatbot tools 清單加入新 tool |
| `pyproject.toml` | 修改 | 加入 python-docx, openpyxl 依賴 |
