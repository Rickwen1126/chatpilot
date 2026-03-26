"""Tests for TimeService singleton."""

from datetime import datetime, timezone

from chatpilot.core.time_service import TimeService


def _fresh() -> TimeService:
    """Create a fresh instance for test isolation."""
    return TimeService("Asia/Taipei")


def test_utc_now_is_utc():
    ts = _fresh()
    now = ts.utc_now()
    assert now.tzinfo == timezone.utc


def test_now_is_local():
    ts = _fresh()
    now = ts.now()
    offset = now.utcoffset()
    assert offset is not None
    assert offset.total_seconds() == 8 * 3600


def test_from_epoch_ms():
    ts = _fresh()
    # 2026-01-01 00:00:00 UTC = 1767225600000 ms
    dt = ts.from_epoch_ms(1767225600000)
    assert dt.tzinfo == timezone.utc
    assert dt.year == 2026
    assert dt.month == 1
    assert dt.day == 1


def test_to_iso_and_from_iso():
    ts = _fresh()
    now = ts.utc_now()
    iso = ts.to_iso(now)
    parsed = ts.from_iso(iso)
    assert abs((parsed - now).total_seconds()) < 1


def test_elapsed_seconds():
    ts = _fresh()
    past = ts.utc_now()
    elapsed = ts.elapsed_seconds(past)
    assert 0 <= elapsed < 1


def test_to_local():
    ts = _fresh()
    utc_dt = datetime(2026, 3, 26, 10, 0, 0, tzinfo=timezone.utc)
    local = ts.to_local(utc_dt)
    assert local.hour == 18  # UTC+8


def test_format_time():
    ts = _fresh()
    utc_dt = datetime(2026, 3, 26, 10, 8, 0, tzinfo=timezone.utc)
    assert ts.format_time(utc_dt) == "18:08"


def test_format_date():
    ts = _fresh()
    utc_dt = datetime(2026, 3, 26, 10, 0, 0, tzinfo=timezone.utc)
    assert ts.format_date(utc_dt) == "2026-03-26"


def test_format_datetime():
    ts = _fresh()
    utc_dt = datetime(2026, 3, 26, 10, 8, 0, tzinfo=timezone.utc)
    assert ts.format_datetime(utc_dt) == "2026-03-26 18:08"


def test_today_string():
    ts = _fresh()
    today = ts.today()
    assert len(today) == 10  # YYYY-MM-DD
    assert today.count("-") == 2


def test_weekday_string():
    ts = _fresh()
    wd = ts.weekday()
    assert wd.startswith("週")


def test_system_prompt_hint():
    ts = _fresh()
    hint = ts.system_prompt_hint()
    assert "台北時間" in hint
    assert "UTC+8" in hint
    assert "[系統時間]" in hint


def test_system_prompt_hint_different_tz():
    ts = TimeService("Asia/Tokyo")
    hint = ts.system_prompt_hint()
    assert "東京時間" in hint
    assert "UTC+9" in hint


def test_singleton_init():
    TimeService.init("Asia/Taipei")
    ts = TimeService.get()
    assert ts.tz_name == "Asia/Taipei"
    # Cleanup: reset singleton
    TimeService._instance = None


def test_singleton_auto_create():
    TimeService._instance = None
    ts = TimeService.get()
    assert ts.tz_name == "Asia/Taipei"
    TimeService._instance = None
