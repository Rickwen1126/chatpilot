"""TimeService — singleton for all time operations.

Nobody should import datetime to calculate time themselves.
要時間找 TimeService。
"""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

# ── Weekday names ────────────────────────────────────────────────
_WEEKDAY_NAMES = ["週一", "週二", "週三", "週四", "週五", "週六", "週日"]

# ── UTC+offset display names for common zones ───────────────────
_TZ_DISPLAY: dict[str, str] = {
    "Asia/Taipei": "台北時間",
    "Asia/Tokyo": "東京時間",
    "Asia/Shanghai": "北京時間",
    "Asia/Hong_Kong": "香港時間",
    "America/New_York": "紐約時間",
    "America/Los_Angeles": "洛杉磯時間",
    "Europe/London": "倫敦時間",
    "UTC": "UTC",
}


class TimeService:
    """Stateless time utility — singleton, configured once at startup."""

    _instance: TimeService | None = None

    def __init__(self, tz_name: str = "Asia/Taipei") -> None:
        self._tz = ZoneInfo(tz_name)
        self._tz_name = tz_name

    @classmethod
    def init(cls, tz_name: str = "Asia/Taipei") -> None:
        """Initialize the singleton. Call once at startup."""
        cls._instance = cls(tz_name)

    @classmethod
    def get(cls) -> TimeService:
        """Get the singleton. Auto-creates with defaults if not initialized."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ── UTC (internal) ───────────────────────────────────────────

    def utc_now(self) -> datetime:
        """Current time in UTC (for internal use, DB storage, diff calc)."""
        return datetime.now(timezone.utc)

    def from_epoch_ms(self, ms: int) -> datetime:
        """Convert epoch milliseconds (e.g. LINE timestamp) to UTC datetime."""
        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)

    def to_iso(self, dt: datetime) -> str:
        """Convert datetime to UTC ISO string (for DB storage)."""
        return dt.astimezone(timezone.utc).isoformat()

    def from_iso(self, s: str) -> datetime:
        """Parse ISO string back to UTC-aware datetime."""
        return datetime.fromisoformat(s).astimezone(timezone.utc)

    def elapsed_seconds(self, since: datetime) -> float:
        """Seconds elapsed since a given UTC datetime."""
        return (self.utc_now() - since).total_seconds()

    # ── User timezone (display) ──────────────────────────────────

    def now(self) -> datetime:
        """Current time in configured user timezone."""
        return datetime.now(self._tz)

    def today(self) -> str:
        """Today's date string in user timezone: '2026-03-26'."""
        return self.now().strftime("%Y-%m-%d")

    def weekday(self) -> str:
        """Current weekday name in user timezone: '週四'."""
        return _WEEKDAY_NAMES[self.now().weekday()]

    def to_local(self, dt: datetime) -> datetime:
        """Convert any aware datetime to user timezone."""
        return dt.astimezone(self._tz)

    def format_time(self, dt: datetime) -> str:
        """Format as local time: '19:08'."""
        return self.to_local(dt).strftime("%H:%M")

    def format_date(self, dt: datetime) -> str:
        """Format as local date: '2026-03-26'."""
        return self.to_local(dt).strftime("%Y-%m-%d")

    def format_datetime(self, dt: datetime) -> str:
        """Format as local datetime: '2026-03-26 19:08'."""
        return self.to_local(dt).strftime("%Y-%m-%d %H:%M")

    # ── Agent hints (dynamic from config) ────────────────────────

    def system_prompt_hint(self) -> str:
        """Generate system prompt time hint from config timezone.

        Config timezone="Asia/Taipei" →
        "[系統時間] 現在是 2026-03-26 19:08（週四）。
         所有工具回傳的時間是台北時間(UTC+8)，不需要自行轉換。"
        """
        now = self.now()
        wd = _WEEKDAY_NAMES[now.weekday()]
        offset = now.utcoffset()
        offset_hours = int(offset.total_seconds() // 3600) if offset else 0
        sign = "+" if offset_hours >= 0 else ""
        tz_display = _TZ_DISPLAY.get(self._tz_name, self._tz_name)

        return (
            f"[系統時間] 現在是 {now.strftime('%Y-%m-%d %H:%M')}（{wd}）。"
            f"所有工具回傳的時間是{tz_display}(UTC{sign}{offset_hours})，"
            f"不需要自行轉換。"
        )

    @property
    def tz_name(self) -> str:
        """The configured timezone name (e.g. 'Asia/Taipei')."""
        return self._tz_name
