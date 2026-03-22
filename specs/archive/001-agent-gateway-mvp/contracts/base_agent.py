"""
BaseAgent 介面合約 — Agent Gateway MVP

所有 agent 必須實作此 Protocol。
Dispatcher 只依賴此介面，不依賴任何具體 agent 實作。

架構原則：
  - Agent 只接收 Message（platform-agnostic）、回傳 Response
  - Agent 不得讀取 Message.platform_context（channel-agnostic 原則）
  - Agent 透過 Copilot SDK 執行；session 管理由 SessionManager 負責

實作路徑：src/chatpilot/agents/base.py（Protocol）
           src/chatpilot/agents/{name}/__init__.py（各 agent 實作）
"""

from typing import Protocol, runtime_checkable

from .types import Message, Response


# ─── BaseAgent Protocol ────────────────────────────────────────────────────


@runtime_checkable
class BaseAgent(Protocol):
    @property
    def name(self) -> str:
        """
        Agent 識別名稱。
        對應 RouteRule.keywords[n].agent_name 與 RouteRule.fallback_agent。
        命名規則：kebab-case，例："general-agent"、"warehouse-agent"
        """
        ...

    async def handle(self, message: Message, session_id: str) -> Response:
        """
        處理訊息並透過 Copilot SDK 產生回應。

        實作方需：
        1. 以 session_id 呼叫 session_manager.resume_session() 恢復或建立 session
        2. 呼叫 session.send() 並等待回應（透過 event handler）
        3. 將 SDK 回應封裝為 Response 回傳

        Args:
            message: 統一輸入訊息（不含平台特有資料）
            session_id: Session 識別碼："{platform}-{conversationId|userId}"

        Returns:
            Agent 的回應

        Raises:
            AgentError: 若 SDK 或下游服務錯誤
        """
        ...


# ─── AgentRegistry ──────────────────────────────────────────────────────

AgentRegistry = dict[str, BaseAgent]
"""BaseAgent 的對應表。key：agent 名稱（對應 BaseAgent.name）"""
