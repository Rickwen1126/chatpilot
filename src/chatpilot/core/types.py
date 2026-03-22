"""Core types for Agent Gateway v2."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum, IntEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

# ── Enums ─────────────────────────────────────────────────────────────


class TaskStatus(str, Enum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"


class ContextMessageType(str, Enum):
    background = "background"
    mention_busy = "mention_busy"


class AccessLevel(IntEnum):
    GLOBAL = 1
    CHATBOT_ONLY = 2
    AGENT_TEAM_ONLY = 3
    AGENT_TEAM_TRIGGER = 4  # chatbot 可用，觸發 async task，pipeline 禁用


# ── Message / Response ────────────────────────────────────────────────


class Message(BaseModel):
    """Unified inbound message from any platform."""

    text: str
    user_id: str
    user_name: str = ""
    platform: str
    group_id: str | None = None
    conversation_id: str
    is_mention: bool = False
    platform_context: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("text")
    @classmethod
    def text_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("text must not be empty after strip")
        return v

    @field_validator("platform")
    @classmethod
    def platform_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("platform must not be empty")
        return v


class Attachment(BaseModel):
    """File or image attachment."""

    type: Literal["image", "file"]
    url: str


class Response(BaseModel):
    """Unified outbound response."""

    text: str
    attachments: list[Attachment] = Field(default_factory=list)

    @field_validator("text")
    @classmethod
    def text_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("text must not be empty")
        return v


# ── Routing ───────────────────────────────────────────────────────────


class ChatRoute(BaseModel):
    """Resolved route for a conversation."""

    route_id: str
    chatbot_name: str
    platform: str
    conversation_id: str
    binding_score: int


class Binding(BaseModel):
    """Routing rule that maps match conditions to a chatbot."""

    match: dict[str, str] = Field(default_factory=dict)
    chatbot: str


class MatchWeights(BaseModel):
    """Scoring weights for binding dimensions."""

    group_id: int = 10
    user_id: int = 8
    platform: int = 5


# ── Config ────────────────────────────────────────────────────────────


class ChatbotConfig(BaseModel):
    """Chatbot declaration from config."""

    name: str
    model: str
    system_message: str
    tools: list[str] = Field(default_factory=list)
    task_history: bool = False
    context_window: int = 20
    timeout: int = 60


class AgentConfig(BaseModel):
    """Pipeline agent declaration from config."""

    name: str
    model: str
    workdir: str | None = None
    tools: list[str] = Field(default_factory=list)


class SchedulerConfig(BaseModel):
    """Task scheduler settings."""

    concurrent_runners: int = 2
    max_queue_size: int = 100
    task_timeout: int = 300


# ── Task ──────────────────────────────────────────────────────────────


class TaskInfo(BaseModel):
    """Async task managed by the scheduler."""

    id: str
    status: TaskStatus = TaskStatus.queued
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_ms: int | None = None
    pipeline_name: str
    input_summary: str
    input_data: dict[str, Any]
    output_summary: str | None = None
    output_full: dict[str, Any] | None = None
    chat_route_id: str
    error: str | None = None


# ── Context Buffer ────────────────────────────────────────────────────


class ContextMessage(BaseModel):
    """Single entry in a context buffer."""

    user_id: str
    user_name: str
    text: str
    timestamp: datetime
    message_type: ContextMessageType


# ── Pipeline ──────────────────────────────────────────────────────────


class NodeOutput(BaseModel):
    """Standard output from a pipeline node."""

    status: Literal["success", "error"]
    data: Any
    error: str | None = None


# ── Tool Registry ────────────────────────────────────────────────────


class ToolDefinition(BaseModel):
    """Registered tool in the ToolFactory."""

    model_config = {"arbitrary_types_allowed": True}

    name: str
    description: str
    parameters: dict[str, Any]
    handler: Any
    access_level: AccessLevel
