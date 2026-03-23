# Warehouse Query Tool Spec

為 chatpilot 新增倉庫查詢工具，讓 LINE 使用者可以用自然語言查庫存。

## 目標

使用者在 LINE 問「虹牌450在哪」→ chatpilot 查倉庫 DB → 回覆自然語言 + 平面圖標示位置。

## 倉庫 Backend API

Base URL: `http://localhost:8000/api/v1`（同機器直連，不走 tunnel）
Web App: `https://warehouse.shinyipaint.com.tw`（Cloudflare Tunnel → localhost:5173）

### 主要查詢 endpoints

```
GET /items/search?q=<keyword>
  - 多關鍵字 AND 搜尋（名稱+描述）
  - 回傳: [{id, unit_id, layer_key, name, description, quantity, unit_of_measure, material_id, material:{id,name,brand}, location_display, layer_display}]
  - limit 50

GET /materials?search=<query>&category=<cat>
  - 搜尋物料目錄（名稱、品牌、aliases）
  - 回傳: [{id, name, brand, category, spec, aliases}]

GET /materials/{material_id}/items
  - 查特定物料的所有庫存位置
  - 回傳: items with location info

GET /inventory
  - 完整庫存快照（大量資料，慎用）
  - 回傳: {inventory: {unit_id: {layer_key: [items]}}, aliases: {unit_id: {primary_name, other_names}}}

GET /units/{unit_id}/layers/{layer_key}/items
  - 查特定位置的所有物品
```

### 查詢策略

chatpilot agent 收到查詢後，根據意圖選擇 API：

| 使用者意圖 | 策略 |
|-----------|------|
| 「X 在哪」（找物料位置） | `/items/search?q=X` |
| 「A1有什麼」（查位置內容） | `/units/A1/layers/*/items` 逐層查，或 `/inventory` 篩 |
| 「立邦的漆都在哪」（品牌查詢） | `/materials?search=立邦` → 取 IDs → `/materials/{id}/items` |
| 「庫存快沒的」（低庫存） | `/inventory` → 篩 quantity < threshold |

## 倉庫佈局（回覆用）

38 個位置，7 個區域：
- AB 排（中央左側）: A1-A4, B1-B4 — 3 層
- CD 排（中央右側）: C1-C4, D1-D4 — 4 層
- H 排（頂部橫排）: H1-H5 — 4 層，不銹鋼
- E 排（左側直排）: E1-E7 — 5 層
- J 排（左側上方）: J1-J3 — 5 層
- 平面區: I, G, F1-F2, K1-K3, L
- 1F: M（4層+6抽屜）, N（平面）

## 回覆格式

### 文字回覆（含 deep link）
```
虹牌450 水性水泥漆 找到 2 個位置：

📍 A2 第2層 — 3罐（白色）
📍 B3 第1層 — 2罐（象牙色）

共 5 罐

👉 https://warehouse.shinyipaint.com.tw/#/search?q=虹牌450
```

Deep link 格式：`https://warehouse.shinyipaint.com.tw/#/search?q={URL encoded query}`
前端 SearchPage 會自動讀取 `q` 參數並執行搜尋。

### 圖片回覆（zone 平面圖）

靜態 zone 圖片存放在 warehouse backend：
`backend/data/zone_images/floor_plan_{zone_id}.png`

可用圖片：
- `floor_plan_overview.png` — 全覽（無高亮）
- `floor_plan_zone_AB.png` — 中央左側 A1-A4, B1-B4
- `floor_plan_zone_CD.png` — 中央右側 C1-C4, D1-D4
- `floor_plan_zone_H.png` — 頂部橫排 H1-H5
- `floor_plan_zone_E.png` — 左側直排 E1-E7
- `floor_plan_zone_J.png` — 左側上方 J1-J3
- `floor_plan_zone_flat.png` — 平面區
- `floor_plan_zone_1F.png` — 1F 區域

unit_id → zone 對應：
```python
UNIT_TO_ZONE = {
    "A1": "zone_AB", "A2": "zone_AB", "A3": "zone_AB", "A4": "zone_AB",
    "B1": "zone_AB", "B2": "zone_AB", "B3": "zone_AB", "B4": "zone_AB",
    "C1": "zone_CD", "C2": "zone_CD", "C3": "zone_CD", "C4": "zone_CD",
    "D1": "zone_CD", "D2": "zone_CD", "D3": "zone_CD", "D4": "zone_CD",
    "H1": "zone_H", "H2": "zone_H", "H3": "zone_H", "H4": "zone_H", "H5": "zone_H",
    "E1": "zone_E", "E2": "zone_E", "E3": "zone_E", "E4": "zone_E",
    "E5": "zone_E", "E6": "zone_E", "E7": "zone_E",
    "J1": "zone_J", "J2": "zone_J", "J3": "zone_J",
    "I": "zone_flat", "G": "zone_flat", "F1": "zone_flat", "F2": "zone_flat",
    "K1": "zone_flat", "K2": "zone_flat", "K3": "zone_flat", "L": "zone_flat",
    "M": "zone_1F", "N": "zone_1F",
}
```

圖片取得方式：直接從 backend 檔案系統讀取，或加一個 API endpoint serve 圖片。
如果結果跨多個 zone，發 overview 圖。

## 實作建議

### 方式：建為 chatpilot tool

建 `src/chatpilot/tools/builtin/warehouse_query.py`：

```python
# Tool definition
ToolDefinition(
    name="warehouse_query",
    description="查詢信益倉庫庫存位置和數量",
    parameters={
        "query": {"type": "string", "description": "搜尋關鍵字（物料名稱、品牌、色號等）"},
        "query_type": {"type": "string", "enum": ["search", "location", "brand", "low_stock"], "default": "search"},
    },
    access_level=AccessLevel.GLOBAL,
)
```

### 注意事項
- LINE 訊息上限 5000 字，查詢結果可能很長要截斷
- 圖片用 image message 回傳（已支援）
- 倉庫 API 同機器 localhost:8000 直連
- 回覆一定要帶 deep link URL，讓使用者可以點進 web app 看詳細
- zone 圖片選擇邏輯：結果在同一 zone → 發該 zone 圖；跨 zone → 發 overview
