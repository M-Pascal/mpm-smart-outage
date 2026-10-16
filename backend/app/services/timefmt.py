"""Human-friendly local time formatting for customer messages."""
from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo


def to_local(dt: datetime, tz: str) -> datetime:
    return dt.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(tz))


def fmt_date(dt: datetime, tz: str) -> str:
    local = to_local(dt, tz)
    return f"{local.day} {local:%B %Y}"


def fmt_time(dt: datetime, tz: str) -> str:
    local = to_local(dt, tz)
    hour = local.hour % 12 or 12
    return f"{hour}:{local:%M} {'AM' if local.hour < 12 else 'PM'}"


def fmt_minutes(minutes: float) -> str:
    minutes = int(round(minutes))
    if minutes >= 1440 and minutes % 1440 == 0:
        d = minutes // 1440
        return f"{d} day{'s' if d != 1 else ''}"
    if minutes >= 60:
        h, m = divmod(minutes, 60)
        label = f"{h} hour{'s' if h != 1 else ''}"
        return f"{label} {m} minutes" if m else label
    return f"{minutes} minute{'s' if minutes != 1 else ''}"
