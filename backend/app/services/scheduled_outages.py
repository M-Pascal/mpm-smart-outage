"""Planned interruptions and their advance notifications."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..clock import now as clock_now
from ..errors import conflict, invalid
from ..models import MiniGrid, NotificationJob, ScheduledOutage, ServiceArea
from . import activity, notifications, settings_store
from .notifications import REASON_LABELS
from .timefmt import fmt_date, fmt_minutes, fmt_time

PRIORITIES = ("low", "medium", "high", "critical")
EDITABLE_TIMES = ("draft", "scheduled", "notification_queued")
MAX_DURATION = timedelta(days=7)


def code(outage: ScheduledOutage) -> str:
    return f"PO-{outage.id:04d}"


# ---------------------------------------------------------------- planning
def plan_notifications(start_at: datetime, offsets: list[int], send_notice: bool, at: datetime,
                       published: bool = False) -> list[dict[str, Any]]:
    """Exact send times for an event. Advance warnings are never scheduled at/after the start."""
    items: list[dict[str, Any]] = []
    if send_notice and not published:
        ok = start_at > at
        items.append({"kind": "notice", "offset_minutes": None, "send_at": at, "valid": ok,
                      "label": "Initial notice (when published)",
                      "reason": "" if ok else "The interruption has already started"})
    for off in sorted(set(offsets), reverse=True):
        send_at = start_at - timedelta(minutes=off)
        label = f"Reminder {fmt_minutes(off)} before"
        if off <= 0:
            items.append({"kind": "reminder", "offset_minutes": off, "send_at": send_at, "valid": False,
                          "label": label, "reason": "Reminders must be sent before the start time"})
        elif send_at <= at:
            items.append({"kind": "reminder", "offset_minutes": off, "send_at": send_at, "valid": False,
                          "label": label, "reason": f"Skipped: less than {fmt_minutes(off)} remain before the start"})
        else:
            items.append({"kind": "reminder", "offset_minutes": off, "send_at": send_at, "valid": True,
                          "label": label, "reason": ""})
    return items


def _validate(db: Session, *, mini_grid_id: int, area_ids: list[int], start_at: datetime, end_at: datetime,
              reason: str, priority: str, require_future: bool = True) -> list[ServiceArea]:
    if reason not in REASON_LABELS:
        raise invalid(f"reason must be one of: {', '.join(REASON_LABELS)}", "reason")
    if priority not in PRIORITIES:
        raise invalid(f"priority must be one of: {', '.join(PRIORITIES)}", "priority")
    if db.get(MiniGrid, mini_grid_id) is None:
        raise invalid("select a valid mini-grid", "mini_grid_id")
    if not area_ids:
        raise invalid("select at least one affected service area", "service_area_ids")
    areas = db.scalars(select(ServiceArea).where(ServiceArea.id.in_(area_ids))).all()
    if len(areas) != len(set(area_ids)):
        raise invalid("one or more service areas do not exist", "service_area_ids")
    if any(a.mini_grid_id != mini_grid_id for a in areas):
        raise invalid("all service areas must belong to the selected mini-grid", "service_area_ids")
    if end_at <= start_at:
        raise invalid("expected restoration must be after the start time", "end_at")
    if end_at - start_at > MAX_DURATION:
        raise invalid("a planned interruption cannot last longer than 7 days", "end_at")
    if require_future and start_at <= clock_now():
        raise invalid("the start time must be in the future", "start_at")
    return list(areas)


# --------------------------------------------------------------- lifecycle
def create(db: Session, data: dict[str, Any], *, publish_now: bool, actor: str) -> ScheduledOutage:
    areas = _validate(db, mini_grid_id=data["mini_grid_id"], area_ids=data["service_area_ids"],
                      start_at=data["start_at"], end_at=data["end_at"], reason=data["reason"],
                      priority=data["priority"])
    offsets = data.get("reminder_offsets")
    if offsets is None:
        offsets = settings_store.get_section(db, "notifications").default_reminder_offsets
    outage = ScheduledOutage(
        title=data["title"], reason=data["reason"], reason_detail=data.get("reason_detail") or "",
        mini_grid_id=data["mini_grid_id"], start_at=data["start_at"], end_at=data["end_at"],
        description=data.get("description") or "", priority=data["priority"], status="draft",
        reminder_offsets=sorted(set(offsets), reverse=True),
        send_notice_on_publish=data.get("send_notice_on_publish", True), service_areas=areas,
        created_at=clock_now(),
    )
    db.add(outage)
    db.flush()
    activity.log(db, "maintenance_created", f"{code(outage)} “{outage.title}” saved as draft",
                 entity_type="scheduled_outage", entity_id=outage.id)
    if publish_now:
        publish(db, outage, actor=actor)
    else:
        db.commit()
    return outage


def publish(db: Session, outage: ScheduledOutage, *, actor: str) -> ScheduledOutage:
    if outage.status != "draft":
        raise conflict(f"{code(outage)} is already {outage.status}")
    t = clock_now()
    if outage.start_at <= t:
        raise invalid("the start time has already passed; reschedule the event before publishing", "start_at")
    outage.status = "scheduled"
    outage.published_at = t
    area_ids = [a.id for a in outage.service_areas]
    for item in plan_notifications(outage.start_at, outage.reminder_offsets, outage.send_notice_on_publish, t):
        if not item["valid"]:
            continue
        if item["kind"] == "notice":
            notifications.create_job(db, kind="notice", template_key="scheduled_maintenance_notice",
                                     area_ids=area_ids, send_at=t, outage=outage, created_by=actor)
        else:
            notifications.create_job(db, kind="reminder", template_key="maintenance_reminder", area_ids=area_ids,
                                     send_at=item["send_at"], offset_minutes=item["offset_minutes"], outage=outage,
                                     created_by=actor)
    activity.log(db, "maintenance_scheduled",
                 f"{code(outage)} “{outage.title}” scheduled for {fmt_date(outage.start_at, _tz(db))} "
                 f"{fmt_time(outage.start_at, _tz(db))}", severity="info", entity_type="scheduled_outage",
                 entity_id=outage.id)
    refresh_status(db, outage, t)
    db.commit()
    notifications.process_due(db, t)  # send the initial notice right away
    refresh_status(db, outage, clock_now())
    db.commit()
    return outage


def pending_jobs(db: Session, outage: ScheduledOutage) -> list[NotificationJob]:
    return list(db.scalars(select(NotificationJob).where(NotificationJob.scheduled_outage_id == outage.id,
                                                         NotificationJob.status.in_(notifications.PENDING))))


def update(db: Session, outage: ScheduledOutage, data: dict[str, Any], *, notify_customers: bool,
           actor: str) -> dict[str, Any]:
    if outage.status in ("completed", "cancelled"):
        raise conflict(f"{code(outage)} is {outage.status} and can no longer be edited")
    t = clock_now()
    in_progress = outage.status == "in_progress"
    if in_progress and set(data) - {"end_at", "description"}:
        raise conflict("an interruption in progress can only have its restoration time or description changed")

    new_start = data.get("start_at", outage.start_at)
    new_end = data.get("end_at", outage.end_at)
    new_areas_ids = data.get("service_area_ids", [a.id for a in outage.service_areas])
    mini_grid_id = data.get("mini_grid_id", outage.mini_grid_id)
    times_changed = new_start != outage.start_at or new_end != outage.end_at
    areas = _validate(db, mini_grid_id=mini_grid_id, area_ids=new_areas_ids, start_at=new_start, end_at=new_end,
                      reason=data.get("reason", outage.reason), priority=data.get("priority", outage.priority),
                      require_future=(new_start != outage.start_at) and not in_progress)
    if in_progress and new_end <= t:
        raise invalid("the new restoration time must be in the future", "end_at")

    tz = _tz(db)
    old = {"old_date": fmt_date(outage.start_at, tz), "old_start_time": fmt_time(outage.start_at, tz),
           "old_end_time": fmt_time(outage.end_at, tz)}
    old_area_ids = {a.id for a in outage.service_areas}

    for field in ("title", "reason", "reason_detail", "description", "priority", "mini_grid_id",
                  "send_notice_on_publish"):
        if field in data and data[field] is not None:
            setattr(outage, field, data[field])
    outage.start_at, outage.end_at, outage.service_areas = new_start, new_end, areas
    offsets_changed = "reminder_offsets" in data and data["reminder_offsets"] is not None \
        and sorted(set(data["reminder_offsets"]), reverse=True) != outage.reminder_offsets
    if offsets_changed:
        outage.reminder_offsets = sorted(set(data["reminder_offsets"]), reverse=True)

    changes = {"reminders_updated": 0, "reminders_cancelled": 0, "reminders_created": 0,
               "announcement_job_ids": []}
    if outage.status != "draft" and not in_progress:
        changes.update(_recalculate_reminders(db, outage, t, actor))
        new_area_ids = {a.id for a in areas}
        for job in pending_jobs(db, outage):
            job.area_ids = sorted(new_area_ids)
        added, removed = new_area_ids - old_area_ids, old_area_ids - new_area_ids
        if added and outage.customers_notified:
            job = notifications.create_job(db, kind="notice", template_key="scheduled_maintenance_notice",
                                           area_ids=sorted(added), send_at=t, outage=outage, created_by=actor,
                                           note="Service area added to the event")
            changes["announcement_job_ids"].append(job.id)
        if removed and outage.customers_notified and notify_customers:
            job = notifications.create_job(db, kind="cancellation", template_key="maintenance_cancelled",
                                           area_ids=sorted(removed), send_at=t, outage=outage, created_by=actor,
                                           note="Service area removed from the event")
            changes["announcement_job_ids"].append(job.id)

    if times_changed:
        outage.reschedule_count += 1
        activity.log(db, "maintenance_rescheduled",
                     f"{code(outage)} rescheduled from {old['old_date']} {old['old_start_time']} to "
                     f"{fmt_date(new_start, tz)} {fmt_time(new_start, tz)}", severity="warning",
                     entity_type="scheduled_outage", entity_id=outage.id)
        if outage.customers_notified and notify_customers:
            job = notifications.create_job(db, kind="reschedule", template_key="maintenance_rescheduled",
                                           area_ids=[a.id for a in areas], send_at=t, outage=outage,
                                           context=old, created_by=actor)
            changes["announcement_job_ids"].append(job.id)
    else:
        activity.log(db, "maintenance_updated", f"{code(outage)} “{outage.title}” updated",
                     entity_type="scheduled_outage", entity_id=outage.id)
    refresh_status(db, outage, t)
    db.commit()
    if changes["announcement_job_ids"]:
        notifications.process_due(db, t)
        refresh_status(db, outage, clock_now())
        db.commit()
    return changes


def _recalculate_reminders(db: Session, outage: ScheduledOutage, t: datetime, actor: str) -> dict[str, int]:
    plan = {i["offset_minutes"]: i for i in plan_notifications(outage.start_at, outage.reminder_offsets, False, t,
                                                                 published=True)}
    updated = cancelled = created = 0
    seen: set[int] = set()
    for job in pending_jobs(db, outage):
        if job.kind != "reminder":
            continue
        item = plan.get(job.offset_minutes)
        if item and item["valid"] and job.offset_minutes not in seen:
            if job.send_at != item["send_at"]:
                job.send_at = item["send_at"]
                job.note = "Send time recalculated after reschedule"
                updated += 1
            seen.add(job.offset_minutes)
        else:
            notifications.cancel_job(db, job, item["reason"] if item else "Reminder removed from the schedule")
            cancelled += 1
    for off, item in plan.items():
        if item["valid"] and off not in seen and not _already_sent(db, outage, off):
            notifications.create_job(db, kind="reminder", template_key="maintenance_reminder",
                                     area_ids=[a.id for a in outage.service_areas], send_at=item["send_at"],
                                     offset_minutes=off, outage=outage, created_by=actor)
            created += 1
    return {"reminders_updated": updated, "reminders_cancelled": cancelled, "reminders_created": created}


def _already_sent(db: Session, outage: ScheduledOutage, offset: int) -> bool:
    """A reminder already sent for the *current* start time is not re-created."""
    return db.scalar(select(NotificationJob.id).where(
        NotificationJob.scheduled_outage_id == outage.id, NotificationJob.offset_minutes == offset,
        NotificationJob.status == "sent",
        NotificationJob.send_at == outage.start_at - timedelta(minutes=offset))) is not None


def cancel(db: Session, outage: ScheduledOutage, *, reason: str, notify_customers: bool, actor: str) -> dict[str, Any]:
    if outage.status in ("completed", "cancelled"):
        raise conflict(f"{code(outage)} is already {outage.status}")
    t = clock_now()
    cancelled = 0
    for job in pending_jobs(db, outage):
        notifications.cancel_job(db, job, "Event cancelled")
        cancelled += 1
    outage.status, outage.cancelled_at, outage.cancel_reason = "cancelled", t, reason
    job_id = None
    if outage.customers_notified and notify_customers:
        job = notifications.create_job(db, kind="cancellation", template_key="maintenance_cancelled",
                                       area_ids=[a.id for a in outage.service_areas], send_at=t, outage=outage,
                                       created_by=actor)
        job_id = job.id
    activity.log(db, "maintenance_cancelled", f"{code(outage)} “{outage.title}” cancelled"
                 + (f": {reason}" if reason else ""), severity="warning", entity_type="scheduled_outage",
                 entity_id=outage.id)
    db.commit()
    if job_id:
        notifications.process_due(db, t)
    return {"pending_cancelled": cancelled, "announcement_job_id": job_id}


def refresh_status(db: Session, outage: ScheduledOutage, t: datetime) -> str | None:
    """Derive the time-based status. Returns the new status when it changed."""
    if outage.status in ("draft", "cancelled", "completed"):
        return None
    if t >= outage.end_at:
        new = "completed"
    elif t >= outage.start_at:
        new = "in_progress"
    else:
        new = "notification_queued" if any(j.status == "scheduled" for j in pending_jobs(db, outage)) else "scheduled"
    if new == outage.status:
        return None
    previous, outage.status = outage.status, new
    if new == "in_progress":
        for job in pending_jobs(db, outage):
            if job.kind in notifications.ADVANCE_KINDS:
                notifications.cancel_job(db, job, "Skipped: the interruption has started")
        activity.log(db, "maintenance_started", f"{code(outage)} “{outage.title}” is now in progress",
                     severity="warning", entity_type="scheduled_outage", entity_id=outage.id, ts=t)
    elif new == "completed":
        activity.log(db, "maintenance_completed", f"{code(outage)} “{outage.title}” completed",
                     severity="success", entity_type="scheduled_outage", entity_id=outage.id, ts=t)
    return new if previous != new else None


def refresh_all(db: Session, t: datetime) -> None:
    for outage in db.scalars(select(ScheduledOutage).where(
            ScheduledOutage.status.in_(("scheduled", "notification_queued", "in_progress")))):
        refresh_status(db, outage, t)
    db.commit()


def areas_under_planned_outage(db: Session, t: datetime) -> dict[int, ScheduledOutage]:
    result: dict[int, ScheduledOutage] = {}
    for outage in db.scalars(select(ScheduledOutage).where(ScheduledOutage.status == "in_progress")):
        if outage.start_at <= t < outage.end_at:
            for area in outage.service_areas:
                result[area.id] = outage
    return result


def _tz(db: Session) -> str:
    return settings_store.get_section(db, "general").timezone
