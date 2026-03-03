"""
ChannelAdapter 介面合約 — Agent Gateway MVP

所有頻道 adapter 必須實作此 Protocol。
Core 層（Dispatcher）只依賴此介面，不依賴任何具體 adapter 實作。

架構原則：
  - Adapter 負責：平台 webhook 解析、簽章驗證、格式轉換
  - Adapter 不得：包含任何 business logic 或呼叫 agent
  - Core 不得：import 任何 adapter 具體類別

實作路徑：src/chatpilot/channels/adapter.py（Protocol）
           src/chatpilot/channels/line/__init__.py（LINE 實作）
"""

from typing import Protocol, runtime_checkable

from .types import Message, Response


# ─── ChannelAdapter Protocol ──────────────────────────────────────────────


@runtime_checkable
class ChannelAdapter(Protocol):
    @property
    def platform(self) -> str:
        """
        平台識別名稱（對應 Message.platform）。
        例："line"、"telegram"
        """
        ...

    def verify_signature(self, raw_body: bytes, signature: str) -> bool:
        """
        驗證 inbound HTTP request 的簽章。

        Args:
            raw_body: 原始 HTTP body
            signature: 平台提供的簽章 header 值

        Returns:
            True 代表驗證通過；False 代表驗證失敗（應拒絕請求）
        """
        ...

    def parse_messages(self, raw_body: bytes) -> list[Message]:
        """
        將平台 webhook payload 解析為 Message 列表。

        一個 webhook event 可能包含多則訊息（LINE batch events）。
        非文字類型的事件（圖片、語音等）應過濾掉，回傳空列表。

        Args:
            raw_body: 原始 HTTP body

        Returns:
            解析出的 Message 列表；無可處理訊息時回傳 []
        """
        ...

    async def send_response(self, message: Message, response: Response) -> None:
        """
        將 Response 透過平台 API 發送至來源對話。

        Args:
            message: 觸發此回覆的原始 Message（包含 platform_context）
            response: 要發送的回覆內容

        Raises:
            AdapterError: 若平台 API 呼叫失敗
        """
        ...

    async def send_processing_ack(self, message: Message) -> None:
        """
        發送「處理中」通知（reply token 逾時時使用）。

        在 20 秒計時器觸發時呼叫，以當前 reply token 立即回覆使用者，
        告知 agent 正在處理中。

        Args:
            message: 觸發的原始 Message（包含 platform_context）
        """
        ...


# ─── AdapterRegistry ─────────────────────────────────────────────────────

AdapterRegistry = dict[str, ChannelAdapter]
"""ChannelAdapter 的對應表。key：platform 名稱（如 "line"）"""
