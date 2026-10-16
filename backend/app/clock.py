"""Demo clock.

All application time comes from here. In demo mode the presenter can move the
clock forward (e.g. to trigger a reminder scheduled for tomorrow). The offset is
persisted in app settings so it survives restarts.

Times are naive UTC datetimes throughout the backend; the API serialises them
with a trailing "Z".
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone


def real_utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class DemoClock:
    def __init__(self) -> None:
        self.offset = timedelta(0)

    def now(self) -> datetime:
        return real_utcnow() + self.offset

    def set_offset_seconds(self, seconds: float) -> None:
        self.offset = timedelta(seconds=seconds)


CLOCK = DemoClock()


def now() -> datetime:
    return CLOCK.now()


def to_naive_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def iso(dt: datetime | None) -> str | None:
    return None if dt is None else dt.replace(microsecond=(dt.microsecond // 1000) * 1000).isoformat() + "Z"
