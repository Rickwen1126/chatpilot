"""
核心型別定義 — Agent Gateway MVP

這些型別定義了三層架構中各層之間的統一合約：
  Channel Layer → (Message) → Core Layer → (Response) → Channel Layer

注意：此為設計合約文件，非實際 source code。
實際實作路徑：src/chatpilot/core/types.py
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# ─── 平台標識 ──────────────────────────────────────────────────────────────

Platform = Literal["line"] | str  # 可擴充至 "telegram" | "web" 等


# ─── Message：統一輸入格式 ─────────────────────────────────────────────────


class LinePlatformContext(BaseModel):
    """LINE 平台的 context 資料"""

    reply_token: str
    """LINE reply token（60 秒有效期，一次性使用）"""

    message_id: str
    """LINE message ID"""

    timestamp: int
    """Webhook 送達時間（Unix timestamp，毫秒）"""


class Message(BaseModel):
    """統一輸入格式"""

    text: str
    """訊息文字內容（MVP 僅支援文字）"""

    user_id: str
    """使用者識別碼（平台 user ID）"""

    platform: Platform
    """平台標識"""

    conversation_id: str | None = None
    """
    群組/對話識別碼。
    群組訊息：群組 ID（LINE 的 groupId 或 roomId）。
    私聊訊息：None（路由以 user_id 作為 fallback key）。
    """

    platform_context: LinePlatformContext | dict = Field(default_factory=dict)
    """
    平台特有的 context 資料。
    Channel Adapter 負責填入；Core 層不得直接讀取此欄位。
    Agent 層不得存取此欄位（channel-agnostic 原則）。
    """


# ─── Response：統一輸出格式 ────────────────────────────────────────────────


class Attachment(BaseModel):
    type: Literal["image", "file"]
    url: str


class Response(BaseModel):
    """統一輸出格式"""

    text: str
    """回覆文字內容"""

    attachments: list[Attachment] = Field(default_factory=list)
    """附件清單。MVP 階段永遠為空 list，保留欄位供未來擴充。"""


# ─── RouteMap：路由表 ──────────────────────────────────────────────────────


class KeywordMapping(BaseModel):
    keyword: str
    """比對字串（substring 比對，大小寫敏感）"""

    agent_name: str
    """命中時路由至此 agent 名稱"""


class RouteRule(BaseModel):
    platform: Platform
    """平台標識"""

    conversation_id: str | None = None
    """群組/對話識別碼。None 代表私聊規則。"""

    keywords: list[KeywordMapping] = Field(default_factory=list)
    """關鍵字 → agent 對應清單（按順序比對，substring match）"""

    fallback_agent: str | None = None
    """Fallback agent 名稱。None = 靜默忽略（不消耗 AI token）。"""


class RouteMap(BaseModel):
    routes: list[RouteRule] = Field(default_factory=list)


# ─── PendingMessage：逾時暫存項目 ─────────────────────────────────────────


class PendingMessage(BaseModel):
    session_id: str
    """Session 識別碼："{platform}-{conversationId}" 或 "{platform}-{userId}" """

    content: str
    """Agent 已完成的回覆文字（待補送）"""

    enqueued_at: int
    """進入佇列的時間（Unix timestamp，毫秒）"""

    ttl_ms: int = 1_800_000
    """訊息有效期（毫秒）。預設 30 分鐘。超過後靜默丟棄。"""


# ─── DispatchResult：路由決策結果（供 logging 使用）─────────────────────────


class KeywordMatch(BaseModel):
    kind: Literal["keyword"] = "keyword"
    agent_name: str
    keyword: str


class FallbackMatch(BaseModel):
    kind: Literal["fallback"] = "fallback"
    agent_name: str


class Ignored(BaseModel):
    kind: Literal["ignored"] = "ignored"
    reason: str = "no_route"
    """忽略原因。例："no_route"（無匹配路由）、"no_fallback"（有路由但無 fallback）"""


DispatchResult = KeywordMatch | FallbackMatch | Ignored
