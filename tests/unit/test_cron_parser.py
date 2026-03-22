"""Tests for cron expression parser."""

from datetime import datetime, timezone

from chatpilot.cron.parser import calculate_next_run, parse_cron


def test_daily_format():
    result = parse_cron("daily 08:00")
    assert result.hour == 8
    assert result.minute == 0
    assert result.tzinfo == timezone.utc


def test_weekly_format():
    result = parse_cron("weekly mon 09:00")
    assert result.weekday() == 0  # Monday
    assert result.hour == 9


def test_interval_minutes():
    before = datetime.now(timezone.utc)
    result = parse_cron("interval 30m")
    assert (result - before).total_seconds() >= 29 * 60


def test_interval_hours():
    before = datetime.now(timezone.utc)
    result = parse_cron("interval 2h")
    assert (result - before).total_seconds() >= 119 * 60


def test_calculate_next_run_after():
    base = datetime(2026, 3, 23, 7, 0, tzinfo=timezone.utc)
    result = calculate_next_run("daily 08:00", after=base)
    assert result.hour == 8
    assert result.day == 23  # same day, 08:00 is after 07:00


def test_calculate_next_run_past_today():
    base = datetime(2026, 3, 23, 9, 0, tzinfo=timezone.utc)
    result = calculate_next_run("daily 08:00", after=base)
    assert result.day == 24  # next day


def test_invalid_format():
    import pytest

    with pytest.raises(ValueError):
        parse_cron("invalid format")


def test_invalid_daily():
    import pytest

    with pytest.raises(ValueError):
        parse_cron("daily 25:00")
