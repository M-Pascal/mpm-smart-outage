"""One scheduler tick: planned statuses -> meter readings -> detection -> due notifications."""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..clock import CLOCK
from ..clock import now as clock_now
from ..db import WRITE_LOCK
from ..models import AreaReading, MeterReading, NotificationJob
from . import monitoring, notifications, scheduled_outages, settings_store

RETENTION = timedelta(days=8)
_tick_counter = {"n": 0}


def tick(db: Session, t: datetime | None = None, *, simulate: bool = True) -> dict:
    with WRITE_LOCK:
        t = t or clock_now()
        scheduled_outages.refresh_all(db, t)
        transitions = []
        if simulate:
            transitions = monitoring.simulate_tick(db, t)
            monitoring.incidents_tick(db, t)
        db.commit()
        sent = notifications.process_due(db, t)
        scheduled_outages.refresh_all(db, clock_now())
        _tick_counter["n"] += 1
        if _tick_counter["n"] % 200 == 0:
            prune(db, t)
        return {"at": t, "transitions": len(transitions), "notifications_sent": sent}


def prune(db: Session, t: datetime) -> None:
    cutoff = t - RETENTION
    db.execute(delete(MeterReading).where(MeterReading.ts < cutoff))
    db.execute(delete(AreaReading).where(AreaReading.ts < cutoff))
    db.commit()


# ------------------------------------------------------------- demo clock
def load_clock(db: Session) -> None:
    CLOCK.set_offset_seconds(settings_store.get_section(db, "demo").clock_offset_seconds)


def set_clock_offset(db: Session, seconds: float) -> None:
    with WRITE_LOCK:
        settings_store.update_section(db, "demo", {"clock_offset_seconds": max(0.0, seconds)})
        db.commit()
        CLOCK.set_offset_seconds(max(0.0, seconds))


def advance(db: Session, minutes: float) -> dict:
    set_clock_offset(db, CLOCK.offset.total_seconds() + minutes * 60)
    return tick(db)


def next_scheduled_job(db: Session) -> NotificationJob | None:
    return db.scalar(select(NotificationJob).where(NotificationJob.status == "scheduled")
                     .order_by(NotificationJob.send_at).limit(1))


def advance_to_next_notification(db: Session) -> dict:
    job = next_scheduled_job(db)
    if job is None:
        return {"advanced": False, "reason": "No scheduled notifications"}
    delta = (job.send_at - clock_now()).total_seconds() + 1
    if delta > 0:
        set_clock_offset(db, CLOCK.offset.total_seconds() + delta)
    result = tick(db)
    return {"advanced": True, "job_id": job.id, **result}
