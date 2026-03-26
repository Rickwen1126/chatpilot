# 倉庫 Item 容量欄位建議

> **日期：** 2026-03-26
> **狀態：** 提案
> **影響：** warehouse-app backend + chatpilot warehouse tool

---

## 問題

目前 item 的容量資訊埋在 `description` 文字裡（如 `"1加侖, 鐵罐"`），無法精確搜尋或過濾。使用者問「有哪些 1L 的」或「加侖裝的龍泰」，搜尋引擎只能做全文比對，準度差。

`unit_of_measure` 是「計數單位」（桶/罐/包），不是「容量」。兩者不同。

## 建議

### Item schema 新增欄位

```python
# 新增兩個欄位
capacity: str | null        # 人讀格式："1L", "5加侖", "18公升", "20kg"
capacity_ml: int | null     # 機讀格式：毫升（方便排序/過濾/比較）
```

### 常見容量對照

| 人讀 | capacity_ml |
|------|-------------|
| 1L | 1000 |
| 4L | 4000 |
| 8L / 8公升 | 8000 |
| 1加侖 | 3785 |
| 5加侖 | 18927 |
| 18公升 | 18000 |
| 20kg | null（重量，不是容量）|

### API 改動

1. **Item model** 加 `capacity` (string, nullable) + `capacity_ml` (integer, nullable)
2. **搜尋 API** 加 capacity 過濾：
   - `GET /items/search?q=龍泰&capacity=1L`
   - 或 `GET /items/search?q=龍泰&capacity_ml_min=1000&capacity_ml_max=4000`
3. **寫入 API** (POST/PUT) 接受 capacity + capacity_ml

### 資料遷移

現有 description 裡的容量資訊可以用 regex 提取：
- `(\d+)\s*加侖` → capacity="N加侖", capacity_ml=N*3785
- `(\d+)\s*[Ll公升]` → capacity="NL", capacity_ml=N*1000
- `(\d+)\s*kg` → capacity="Nkg", capacity_ml=null

建議寫一個 migration script 批次更新。

### chatpilot 端改動

warehouse tool 的 search action 加 capacity 參數傳遞（API 支援後）。tool description 加說明讓 LLM 知道可以按容量搜尋。

---

## 優先順序

1. Backend 加欄位 + migration script
2. 搜尋 API 支援 capacity 過濾
3. chatpilot warehouse tool 接上
