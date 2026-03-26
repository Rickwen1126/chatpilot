from __future__ import annotations

from datetime import datetime, timedelta

from chatpilot.core.time_service import TimeService

_WEEKDAYS = {
    "mon": 0,
    "tue": 1,
    "wed": 2,
    "thu": 3,
    "fri": 4,
    "sat": 5,
    "sun": 6,
}


def parse_cron(expr: str) -> datetime:
    """Parse a simplified cron expression and return the next run time (UTC).

    Supported formats:
        daily HH:MM
        weekly DAY HH:MM
        interval Nm | interval Nh
    """
    return calculate_next_run(expr)


def calculate_next_run(expr: str, after: datetime | None = None) -> datetime:
    """Calculate the next run time after *after* (defaults to now UTC).

    Raises ``ValueError`` for unrecognised or malformed expressions.
    """
    if after is None:
        after = TimeService.get().utc_now()

    parts = expr.strip().split()
    if not parts:
        raise ValueError(f"Invalid cron expression: {expr!r}")

    kind = parts[0].lower()

    if kind == "daily":
        return _parse_daily(parts, after, expr)
    if kind == "weekly":
        return _parse_weekly(parts, after, expr)
    if kind == "interval":
        return _parse_interval(parts, after, expr)

    raise ValueError(f"Invalid cron expression: {expr!r}")


# ---- private helpers --------------------------------------------------------


def _parse_time(raw: str, expr: str) -> tuple[int, int]:
    """Return (hour, minute) from an ``HH:MM`` string."""
    try:
        hour, minute = raw.split(":")
        h, m = int(hour), int(minute)
    except (ValueError, AttributeError):
        raise ValueError(f"Invalid time format in cron expression: {expr!r}")
    if not (0 <= h <= 23 and 0 <= m <= 59):
        raise ValueError(f"Invalid time format in cron expression: {expr!r}")
    return h, m


def _parse_daily(parts: list[str], after: datetime, expr: str) -> datetime:
    if len(parts) != 2:
        raise ValueError(f"Invalid cron expression: {expr!r}")

    h, m = _parse_time(parts[1], expr)
    candidate = after.replace(hour=h, minute=m, second=0, microsecond=0)
    if candidate <= after:
        candidate += timedelta(days=1)
    return candidate


def _parse_weekly(parts: list[str], after: datetime, expr: str) -> datetime:
    if len(parts) != 3:
        raise ValueError(f"Invalid cron expression: {expr!r}")

    day_str = parts[1].lower()
    if day_str not in _WEEKDAYS:
        raise ValueError(f"Invalid day in cron expression: {expr!r}")

    target_weekday = _WEEKDAYS[day_str]
    h, m = _parse_time(parts[2], expr)

    candidate = after.replace(hour=h, minute=m, second=0, microsecond=0)
    days_ahead = (target_weekday - candidate.weekday()) % 7
    candidate += timedelta(days=days_ahead)

    if candidate <= after:
        candidate += timedelta(weeks=1)
    return candidate


def _parse_interval(parts: list[str], after: datetime, expr: str) -> datetime:
    if len(parts) != 2:
        raise ValueError(f"Invalid cron expression: {expr!r}")

    token = parts[1].lower()
    if token.endswith("m"):
        try:
            minutes = int(token[:-1])
        except ValueError:
            raise ValueError(f"Invalid interval in cron expression: {expr!r}")
        if minutes <= 0:
            raise ValueError(f"Invalid interval in cron expression: {expr!r}")
        return after + timedelta(minutes=minutes)

    if token.endswith("h"):
        try:
            hours = int(token[:-1])
        except ValueError:
            raise ValueError(f"Invalid interval in cron expression: {expr!r}")
        if hours <= 0:
            raise ValueError(f"Invalid interval in cron expression: {expr!r}")
        return after + timedelta(hours=hours)

    raise ValueError(f"Invalid interval in cron expression: {expr!r}")
