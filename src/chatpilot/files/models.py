"""Core file models for FileHandleCenter."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class FileKind(str, Enum):
    image = "image"
    audio = "audio"
    video = "video"
    file = "file"


class FetchStatus(str, Enum):
    registered = "registered"
    fetching = "fetching"
    ready = "ready"
    failed = "failed"
    expired = "expired"


class StorageBackend(str, Enum):
    none = "none"
    local = "local"
    r2 = "r2"


class ScanStatus(str, Enum):
    unscanned = "unscanned"
    clean = "clean"
    suspicious = "suspicious"
    failed = "failed"


class RetentionClass(str, Enum):
    default = "default"
    short = "short"
    long = "long"
    permanent = "permanent"


class SourceHandleInput(BaseModel):
    """Adapter-translated source descriptor for an inbound file."""

    route_id: str
    platform: str
    kind: FileKind
    native_locator: str
    filename: str | None = None
    mime_type: str | None = None
    # v1 intentionally keeps locator simple. If a future platform needs a
    # composite locator, extend this schema instead of overloading filenames.
    platform_context: dict[str, Any] = Field(default_factory=dict)

    @field_validator("route_id", "platform", "native_locator")
    @classmethod
    def _not_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("field must not be empty")
        return value


class CanonicalFileHandle(BaseModel):
    """Canonical system file identity after registration."""

    file_id: str
    route_id: str
    platform: str
    native_locator: str
    kind: FileKind
    filename: str | None = None
    mime_type: str | None = None
    platform_context: dict[str, Any] = Field(default_factory=dict)

    @field_validator("file_id", "route_id", "platform", "native_locator")
    @classmethod
    def _required_string(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("field must not be empty")
        return value

    @classmethod
    def from_source(
        cls,
        file_id: str,
        source: SourceHandleInput,
    ) -> CanonicalFileHandle:
        return cls(
            file_id=file_id,
            route_id=source.route_id,
            platform=source.platform,
            native_locator=source.native_locator,
            kind=source.kind,
            filename=source.filename,
            mime_type=source.mime_type,
            platform_context=dict(source.platform_context),
        )


class SourceFetchResult(BaseModel):
    """Raw file fetch result returned by an adapter."""

    data: bytes
    filename: str | None = None
    mime_type: str | None = None
    size_bytes: int | None = None

    @field_validator("data")
    @classmethod
    def _data_not_empty(cls, value: bytes) -> bytes:
        if not value:
            raise ValueError("data must not be empty")
        return value

    def normalized_size_bytes(self) -> int:
        return self.size_bytes if self.size_bytes is not None else len(self.data)


class MaterializedAsset(BaseModel):
    """Materialized asset state after local persistence or external publish."""

    file_id: str
    storage_backend: StorageBackend
    local_path: str | None = None
    public_url: str | None = None
    sha256: str | None = None
    size_bytes: int | None = None
    scan_status: ScanStatus = ScanStatus.unscanned
    materialized_at: datetime | None = None
    expires_at: datetime | None = None
    filename: str | None = None
    mime_type: str | None = None

