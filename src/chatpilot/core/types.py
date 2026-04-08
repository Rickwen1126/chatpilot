"""Core types for Agent Gateway v2."""

from __future__ import annotations

from datetime import datetime
from enum import Enum, IntEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from chatpilot.core.time_service import TimeService
from chatpilot.files.models import CanonicalFileHandle, SourceHandleInput

# ── Enums ─────────────────────────────────────────────────────────────


class TaskStatus(str, Enum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"


class ContextMessageType(str, Enum):
    background = "background"


class AccessLevel(IntEnum):
    GLOBAL = 1
    CHATBOT_ONLY = 2
    AGENT_TEAM_ONLY = 3
    AGENT_TEAM_TRIGGER = 4  # chatbot 可用，觸發 async task，pipeline 禁用
    OBSERVER_ONLY = 5


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
    source_handles: list[SourceHandleInput] = Field(default_factory=list)
    file_handles: list[CanonicalFileHandle] = Field(default_factory=list)
    platform_context: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(
        default_factory=lambda: TimeService.get().utc_now()
    )

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


class DiscoveryEvent(BaseModel):
    """Pre-message route discovery event from a platform webhook."""

    discovery_type: Literal["follow", "join"]
    route_type: Literal["user", "group"]
    platform: str
    conversation_id: str
    timestamp: datetime = Field(
        default_factory=lambda: TimeService.get().utc_now()
    )
    platform_context: dict[str, Any] = Field(default_factory=dict)

    @property
    def route_id(self) -> str:
        return f"{self.platform}:{self.conversation_id}"


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


class SessionContext(BaseModel):
    """Bridge from a runtime session to the delegated target route context.

    `sdk_session_id` identifies the current runtime actor (chatbot session or
    disposable pipeline session). `route_id` identifies the target
    conversation lane whose state/tools this actor is operating on.

    In chatbot mode the runtime actor and target route usually align. In
    pipeline/delegate mode they do not: the pipeline session is only acting on
    behalf of the original route/chatbot context.
    """

    sdk_session_id: str
    route_id: str
    platform: str
    conversation_id: str
    chatbot_name: str


class Binding(BaseModel):
    """Routing rule that maps match conditions to a chatbot."""

    match: dict[str, str] = Field(default_factory=dict)
    chatbot: str
    reply_policy: Literal["never", "addressed"] = "addressed"
    processing_policy: Literal["none", "interactive"] = "interactive"
    observation: ObservationConfig | None = None

    @model_validator(mode="after")
    def validate_policy_combination(self) -> Binding:
        if (
            self.reply_policy == "never"
            and self.processing_policy != "none"
        ):
            raise ValueError(
                "reply_policy=never must be paired with processing_policy=none"
            )
        if (
            self.reply_policy == "addressed"
            and self.processing_policy != "interactive"
        ):
            raise ValueError(
                "reply_policy=addressed must be paired with "
                "processing_policy=interactive"
            )
        return self


class MatchWeights(BaseModel):
    """Scoring weights for binding dimensions."""

    group_id: int = 10
    user_id: int = 8
    platform: int = 5


class RouteGroupConfig(BaseModel):
    """Logical shared/query unit for observer vNext."""

    model_config = {"extra": "allow"}

    description: str = ""

    @model_validator(mode="after")
    def reject_members(self) -> RouteGroupConfig:
        if self.model_extra and "members" in self.model_extra:
            raise ValueError("route_group must not define members")
        return self


class ObservationProfileRetrievalConfig(BaseModel):
    """Query-time retrieval hints for shortlist scoring."""

    description: str = ""
    keywords: list[str] = Field(default_factory=list)


class ObservationProfileConfig(BaseModel):
    """Prompt-backed observation interpretation profile."""

    model_config = {"extra": "allow"}

    mode: Literal["batch"]
    batch_size: int = 10
    instructions: str
    categories: list[str] = Field(default_factory=list)
    retrieval: ObservationProfileRetrievalConfig = Field(
        default_factory=ObservationProfileRetrievalConfig
    )


class ObservationCaptureConfig(BaseModel):
    """Capture target for a binding."""

    group: str
    profile: str


class ObservationConfig(BaseModel):
    """Observation policy attached to a binding."""

    capture: ObservationCaptureConfig | None = None
    consume: list[str] = Field(default_factory=list)


class DiscoveryProfileConfig(BaseModel):
    """Route onboarding policy template applied at discovery time."""

    chatbot: str
    reply_policy: Literal["never", "addressed"] = "addressed"
    processing_policy: Literal["none", "interactive"] = "interactive"
    observation: ObservationConfig | None = None

    @model_validator(mode="after")
    def validate_policy_combination(self) -> DiscoveryProfileConfig:
        if (
            self.reply_policy == "never"
            and self.processing_policy != "none"
        ):
            raise ValueError(
                "discovery_profile reply_policy=never must be paired with "
                "processing_policy=none"
            )
        if (
            self.reply_policy == "addressed"
            and self.processing_policy != "interactive"
        ):
            raise ValueError(
                "discovery_profile reply_policy=addressed must be paired with "
                "processing_policy=interactive"
            )
        return self


class DiscoveryRuleConfig(BaseModel):
    """Rule that selects a discovery profile for a newly discovered route."""

    platform: str | None = None
    route_type: Literal["group", "user"]
    group_id: str | None = None
    user_id: str | None = None
    label_keywords: list[str] = Field(default_factory=list)
    profile: str

    @model_validator(mode="after")
    def validate_route_match_fields(self) -> DiscoveryRuleConfig:
        if self.route_type == "group" and self.user_id:
            raise ValueError(
                "discovery_rule route_type=group must not define user_id"
            )
        if self.route_type == "user" and self.group_id:
            raise ValueError(
                "discovery_rule route_type=user must not define group_id"
            )
        return self


class RouteOnboardingState(BaseModel):
    """Materialized runtime route policy produced by discovery onboarding."""

    route_id: str
    platform: str
    conversation_id: str
    route_type: Literal["group", "user"]
    chatbot: str
    reply_policy: Literal["never", "addressed"]
    processing_policy: Literal["none", "interactive"]
    observation: ObservationConfig | None = None
    label: str | None = None
    profile_name: str | None = None
    discovery_type: Literal["follow", "join"]
    discovered_at: datetime


# ── Config ────────────────────────────────────────────────────────────


class ChatbotConfig(BaseModel):
    """Chatbot declaration from config."""

    name: str
    model: str
    system_message: str
    tools: list[str] = Field(default_factory=list)
    task_history: bool = False
    context_window: int = 20
    timeout: int = 300
    workdir: str | None = None
    auto_trigger_keywords: list[str] = Field(default_factory=list)


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


class CronSchedulerConfig(BaseModel):
    """Cron scheduler settings."""

    tick_interval: int = 60
    available_tools: list[str] = Field(default_factory=list)


class AdapterChannelConfig(BaseModel):
    """Named adapter channel loaded from config."""

    name: str
    channel_secret_env: str
    channel_token_env: str


# ── Task ──────────────────────────────────────────────────────────────


class TaskInfo(BaseModel):
    """Async task managed by the scheduler.

    `chat_route_id` is the target route that owns the task/result path. It is
    not the runtime SDK session identifier of whichever pipeline actor happens
    to execute the task later.
    """

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
    reply_mode: Literal["direct", "via_chatbot"] = "direct"


# ── Context Buffer ────────────────────────────────────────────────────


class ContextMessage(BaseModel):
    """Single entry in a context buffer."""

    user_id: str
    user_name: str
    text: str
    timestamp: datetime
    message_type: ContextMessageType


class ObserverBatchPayload(BaseModel):
    """Structured batch payload handed from observation lane to worker."""

    route_id: str
    captured_profile_name: str
    instructions: str
    categories: list[str] = Field(default_factory=list)
    messages: list[ContextMessage] = Field(default_factory=list)
    formatted_messages: str
    batch_time: datetime = Field(
        default_factory=lambda: TimeService.get().utc_now()
    )


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
