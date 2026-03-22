# Contract: ChannelAdapter Protocol

**對應 FR**: FR-006, FR-007, FR-008

## Protocol 定義

```python
class ChannelAdapter(Protocol):
    """頻道 adapter 介面。每個平台實作此 Protocol。"""

    @property
    def platform(self) -> str:
        """平台標識（如 "line", "mock"）"""
        ...

    async def verify_request(self, request: Request) -> bool:
        """驗證 webhook 請求簽章。

        Args:
            request: FastAPI Request 物件
        Returns:
            True 表示驗證通過
        Raises:
            AdapterError: 簽章驗證失敗
        """
        ...

    async def parse_messages(self, request: Request) -> list[Message]:
        """解析 webhook 請求為統一 Message 格式。

        Args:
            request: FastAPI Request 物件
        Returns:
            Message 列表（一個 webhook 可能包含多則訊息）
        """
        ...

    async def send_reply(self, message: Message, response: Response) -> None:
        """回覆即時訊息（使用 reply token 等機制）。

        Args:
            message: 原始訊息（含 platform_context）
            response: 回應內容
        Raises:
            AdapterError: 發送失敗
        """
        ...

    async def push_message(self, route_id: str, response: Response) -> None:
        """主動推送訊息到指定對話（async task 結果回報）。

        Args:
            route_id: 對話路由 ID（{platform}:{conversation_id}）
            response: 推送內容
        Raises:
            AdapterError: Push 失敗（binding 壞掉等）
        """
        ...
```

## 行為約束

- `verify_request` MUST 在 `parse_messages` 之前呼叫
- `send_reply` 使用平台的即時回覆機制（如 LINE reply token）
- `push_message` 使用平台的主動推送機制（如 LINE Push API）
- Adapter MUST NOT 包含業務邏輯
- Adapter MUST 處理平台特定的截斷 / 分段邏輯

## 實作清單

| Adapter | 優先級 | 說明 |
|---------|--------|------|
| `LineAdapter` | P1 | LINE Messaging API |
| `MockAdapter` | P1 | 測試用 |
| `CliAdapter` | P2 | CLI stdin/stdout |
