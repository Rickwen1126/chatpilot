# Contract: MemoryStore Protocol

**對應 FR**: FR-001 ~ FR-007

## Protocol 定義

```python
class MemoryStore(Protocol):
    """泛用持久化記憶介面。"""

    async def save(self, route_id: str, type: str, data: dict) -> str:
        """儲存一筆記憶。

        Args:
            route_id: 對話路由 ID
            type: 記憶類型（memo, reminder, schedule）
            data: 符合該 type schema 的 dict
        Returns:
            新建的 ID
        Raises:
            ValueError: type 不存在或 data 不符合 schema
        """
        ...

    async def get(self, route_id: str, type: str, id: str) -> dict | None:
        """取得單筆記憶。"""
        ...

    async def list(self, route_id: str, type: str) -> list[dict]:
        """列出指定 route 的所有指定 type 記憶。"""
        ...

    async def delete(self, route_id: str, type: str, id: str) -> bool:
        """刪除一筆記憶。回傳是否有實際刪除。"""
        ...

    async def update(self, route_id: str, type: str, id: str, data: dict) -> None:
        """更新一筆記憶的部分欄位。

        Args:
            data: 要更新的欄位（merge，非全覆蓋）
        """
        ...
```

## 特殊查詢 Methods

```python
class MemoryStore(Protocol):
    # ... CRUD 同上

    async def query_due_before(
        self, type: str, before: datetime
    ) -> list[dict]:
        """查詢 due_at / next_run_at 在指定時間之前的 pending 項目。

        用於 CronScheduler 掃描到期的 reminder / schedule。
        不綁 route_id，掃全部。
        """
        ...
```

## 行為約束

- save 時 MUST 驗證 data 符合 type 的 Pydantic schema
- type MUST 為已註冊的 type（memo / custom_prompt / reminder / schedule）
- route_id + type + id 唯一
- 所有 schema 欄位 MUST 有 default 值（schema 演進安全）
- SQLite 實作 MUST 使用 WAL mode
