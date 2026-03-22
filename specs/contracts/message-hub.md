# Contract: MessageHub Protocol

**對應 FR**: FR-008a ~ FR-008g

## Protocol 定義

```python
class MessageHub(Protocol):
    """中央訊息處理中心。所有訊息進出 MUST 經過 MessageHub。"""

    async def receive(
        self,
        message: Message,
        adapter: ChannelAdapter,
    ) -> None:
        """接收 inbound 訊息，決定放行、攔截、或存入 buffer。

        處理流程：
        1. 群組？→ 是否 @bot？
           - 否 → 存入 context buffer，不回應
           - 是 → chatbot idle？
             - idle → 從 buffer 取出 context，放行給 router
             - busy → 回覆「處理中」，存入 buffer
        2. 私聊？→ chatbot idle？
           - idle → 放行給 router
           - busy → 回覆「處理中」，存入 buffer

        Args:
            message: 統一格式訊息
            adapter: 來源 adapter（用於即時回覆）
        """
        ...

    async def send_reply(
        self,
        message: Message,
        response: Response,
        adapter: ChannelAdapter,
    ) -> None:
        """透過 adapter 發送即時回覆。

        Args:
            message: 原始訊息
            response: 回應內容
            adapter: 目標 adapter
        """
        ...

    async def push(
        self,
        route_id: str,
        response: Response,
    ) -> None:
        """推送 async task 結果回原對話。

        根據 route_id 找到對應 adapter，呼叫 push_message。
        Push 失敗時 log error，不重試（MVP）。

        Args:
            route_id: 對話路由 ID
            response: 推送內容
        """
        ...

    def get_status(self, route_id: str) -> Literal["idle", "busy"]:
        """查詢指定 chatbot 的 busy/idle 狀態。"""
        ...

    def set_busy(self, route_id: str) -> None:
        """標記 chatbot 為 busy。"""
        ...

    def set_idle(self, route_id: str) -> None:
        """標記 chatbot 為 idle。"""
        ...
```

## Context Buffer 介面

```python
class ContextBuffer(Protocol):
    """Per-chatbot 的群組對話 context buffer。"""

    def append(self, route_id: str, ctx_msg: ContextMessage) -> None:
        """新增一條訊息到 buffer（sliding window 自動淘汰舊訊息）。"""
        ...

    def drain(self, route_id: str) -> list[ContextMessage]:
        """取出並清空 buffer 內容（注入 chatbot 後清空）。"""
        ...

    def format_context(self, messages: list[ContextMessage]) -> str:
        """將 buffer 訊息格式化為結構化 context prefix。"""
        ...

    async def flush_to_disk(self, route_id: str) -> None:
        """將 hot layer 寫入 cold layer（disk 持久化）。"""
        ...
```

## 行為約束

- 所有 inbound / reply / push MUST 經過 MessageHub（不可直接呼叫 adapter）
- Busy 期間收到的 @bot 訊息 MUST log + 存入 buffer
- Context buffer drain 後 MUST 清空（避免重複注入）
- Flush 以 `context_window` 為單位觸發
- MVP 實作：InMemoryMessageHub + FileContextBuffer
