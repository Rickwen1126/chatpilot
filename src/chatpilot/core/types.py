"""Core types for the Agent Gateway."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

Platform = Literal["line"] | str


class LinePlatformContext(BaseModel):
    """LINE platform context data."""

    reply_token: str
    message_id: str
    timestamp: int


class Message(BaseModel):
    """Unified input format."""

    text: str
    user_id: str
    platform: Platform
    conversation_id: str | None = None
    platform_context: LinePlatformContext | dict = Field(default_factory=dict)

    @field_validator("text")
    @classmethod
    def text_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("text must not be empty")
        return v

    @field_validator("platform")
    @classmethod
    def platform_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("platform must not be empty")
        return v


class Attachment(BaseModel):
    type: Literal["image", "file"]
    url: str


class Response(BaseModel):
    """Unified output format."""

    text: str
    attachments: list[Attachment] = Field(default_factory=list)

    @field_validator("text")
    @classmethod
    def text_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("text must not be empty")
        return v


class KeywordMapping(BaseModel):
    keyword: str
    agent_name: str = Field(alias="agentName", default="")

    model_config = {"populate_by_name": True}


class RouteRule(BaseModel):
    platform: Platform
    conversation_id: str | None = Field(default=None, alias="conversationId")
    keywords: list[KeywordMapping] = Field(default_factory=list)
    fallback_agent: str | None = Field(default=None, alias="fallbackAgent")
    model: str | None = None

    model_config = {"populate_by_name": True}


class RouteMap(BaseModel):
    routes: list[RouteRule] = Field(default_factory=list)


class PendingMessage(BaseModel):
    session_id: str
    content: str
    enqueued_at: int
    ttl_ms: int = 1_800_000


class KeywordMatch(BaseModel):
    kind: Literal["keyword"] = "keyword"
    agent_name: str
    keyword: str
    model: str | None = None


class FallbackMatch(BaseModel):
    kind: Literal["fallback"] = "fallback"
    agent_name: str
    model: str | None = None


class Ignored(BaseModel):
    kind: Literal["ignored"] = "ignored"
    reason: str = "no_route"


DispatchResult = KeywordMatch | FallbackMatch | Ignored
