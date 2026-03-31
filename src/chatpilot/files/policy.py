"""Retention, scan, and ingress policy helpers for file assets."""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import Enum

from chatpilot.files.models import FileKind, RetentionClass, ScanStatus, SourceHandleInput

RETENTION_WINDOWS: dict[RetentionClass, timedelta | None] = {
    RetentionClass.short: timedelta(days=1),
    RetentionClass.default: timedelta(days=7),
    RetentionClass.long: timedelta(days=30),
    RetentionClass.permanent: None,
}


def compute_expires_at(
    retention_class: RetentionClass | str = RetentionClass.default,
    *,
    from_time: datetime,
) -> datetime | None:
    retention = RetentionClass(retention_class)
    window = RETENTION_WINDOWS[retention]
    if window is None:
        return None
    return from_time + window


def default_scan_status() -> ScanStatus:
    return ScanStatus.unscanned


class IngressAction(str, Enum):
    register_only = "register_only"
    download_now = "download_now"
    prefetch = "prefetch"


def decide_ingress_action(source: SourceHandleInput) -> IngressAction:
    """Default ingress action policy.

    v1 keeps the policy intentionally small: audio should be available before
    STT runs, so it downloads immediately. Other kinds stay lazy until
    explicitly requested by a later workflow.
    """

    if source.kind == FileKind.audio:
        return IngressAction.download_now
    return IngressAction.register_only
