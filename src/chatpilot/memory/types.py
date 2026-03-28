from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    from chatpilot.core.time_service import TimeService

    return TimeService.get().utc_now()


def _uuid() -> str:
    return uuid4().hex


class MemoryStatus(str, Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"


class Memo(BaseModel):
    id: str = Field(default_factory=_uuid)
    route_id: str = ""
    text: str = ""
    tags: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utcnow)


class CustomPrompt(BaseModel):
    id: str = Field(default_factory=_uuid)
    route_id: str = ""
    text: str = ""
    category: str = "general"
    created_at: datetime = Field(default_factory=_utcnow)


class Reminder(BaseModel):
    id: str = Field(default_factory=_uuid)
    route_id: str = ""
    text: str = ""
    due_at: datetime = Field(default_factory=_utcnow)
    status: MemoryStatus = MemoryStatus.pending
    last_error: str | None = None
    created_at: datetime = Field(default_factory=_utcnow)


class Observation(BaseModel):
    id: str = Field(default_factory=_uuid)
    route_id: str = ""
    batch_time: datetime = Field(default_factory=_utcnow)
    message_count: int = 0
    entries: list[dict] = Field(default_factory=list)
    summary: str = ""
    created_at: datetime = Field(default_factory=_utcnow)


class TriggerKeyword(BaseModel):
    id: str = Field(default_factory=_uuid)
    route_id: str = ""
    keyword: str = ""
    created_at: datetime = Field(default_factory=_utcnow)


class Schedule(BaseModel):
    id: str = Field(default_factory=_uuid)
    route_id: str = ""
    cron_expr: str = ""
    tool_name: str = ""
    chatbot_name: str = ""
    input_data: dict = Field(default_factory=dict)
    status: MemoryStatus = MemoryStatus.pending
    last_run_at: datetime | None = None
    next_run_at: datetime = Field(default_factory=_utcnow)
    last_error: str | None = None
    created_at: datetime = Field(default_factory=_utcnow)
