"""Operator actions on unexpected-outage incidents."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..clock import now as clock_now
from ..errors import conflict, invalid
from ..models import Incident, IncidentEvent, NotificationJob
from . import activity, notifications, settings_store


def code(inc: Incident) -> str:
    return f"INC-{inc.id:04d}"


def _event(db: Session, inc: Incident, type_: str, message: str, actor: str, t: datetime | None = None) -> None:
    db.add(IncidentEvent(incident_id=inc.id, ts=t or clock_now(), type=type_, message=message, actor=actor))


def _require_open(inc: Incident, action: str) -> None:
    if inc.resolution_status == "resolved":
        raise conflict(f"{code(inc)} is already resolved; cannot {action}")


def confirm(db: Session, inc: Incident, *, method: str, actor: str, notify_customers: bool, note: str = "") -> NotificationJob | None:
    if inc.verification_status == "confirmed":
        raise conflict(f"{code(inc)} is already confirmed")
    if inc.verification_status == "rejected":
        raise conflict(f"{code(inc)} was rejected")
    _require_open(inc, "confirm it")
    t = clock_now()
    inc.verification_status, inc.confirmation_method, inc.confirmed_at = "confirmed", method, t
    if inc.scope == "meter" and method == "manual":
        inc.scope = "area"  # the operator has decided this affects the service area
    how = "automatically (sufficient monitoring evidence)" if method == "auto" else f"manually by {actor}"
    _event(db, inc, "confirmed", f"Outage confirmed {how}" + (f": {note}" if note else ""), actor, t)
    activity.log(db, "outage_confirmed", f"{code(inc)} confirmed {how} in {inc.service_area.name}",
                 severity="critical", entity_type="incident", entity_id=inc.id, operator_alert=True, ts=t)
    job = None
    if notify_customers:
        job = notifications.create_job(db, kind="outage_alert", template_key="unexpected_outage",
                                       area_ids=[inc.service_area_id], send_at=t, incident=inc, created_by=actor)
        _event(db, inc, "notification", f"Customer outage alert queued for {job.recipients_count} customers", actor, t)
    db.commit()
    if job:
        notifications.send_job(db, job)
    return job


def acknowledge(db: Session, inc: Incident, actor: str) -> None:
    if inc.acknowledged_at:
        raise conflict(f"{code(inc)} was already acknowledged by {inc.acknowledged_by}")
    t = clock_now()
    inc.acknowledged_at, inc.acknowledged_by = t, actor
    _event(db, inc, "acknowledged", f"Acknowledged by {actor}", actor, t)
    activity.log(db, "incident_acknowledged", f"{code(inc)} acknowledged by {actor}", entity_type="incident",
                 entity_id=inc.id, ts=t)
    db.commit()


def investigate(db: Session, inc: Incident, actor: str, note: str = "") -> None:
    _require_open(inc, "start an investigation")
    if inc.resolution_status == "investigating":
        raise conflict(f"{code(inc)} is already under investigation")
    t = clock_now()
    inc.resolution_status = "investigating"
    if not inc.acknowledged_at:
        inc.acknowledged_at, inc.acknowledged_by = t, actor
    _event(db, inc, "investigating", "Investigation started" + (f": {note}" if note else ""), actor, t)
    activity.log(db, "incident_investigating", f"{code(inc)}: investigation started by {actor}",
                 entity_type="incident", entity_id=inc.id, ts=t)
    db.commit()


def reject(db: Session, inc: Incident, actor: str, reason: str) -> None:
    _require_open(inc, "reject it")
    if inc.verification_status == "confirmed":
        raise conflict(f"{code(inc)} is confirmed; resolve it instead of rejecting")
    t = clock_now()
    inc.verification_status = "rejected"
    inc.resolution_status, inc.resolved_at = "resolved", t
    inc.resolution_note = reason or "Rejected by operator (false alarm)"
    _event(db, inc, "rejected", f"Rejected as a false alarm: {inc.resolution_note}", actor, t)
    activity.log(db, "incident_rejected", f"{code(inc)} rejected by {actor}", entity_type="incident",
                 entity_id=inc.id, ts=t)
    db.commit()


def close(db: Session, inc: Incident, t: datetime, *, note: str, actor: str = "system") -> None:
    inc.resolution_status, inc.resolved_at, inc.resolution_note = "resolved", t, note
    _event(db, inc, "resolved", note, actor, t)
    activity.log(db, "outage_resolved", f"{code(inc)} in {inc.service_area.name} resolved", severity="success",
                 entity_type="incident", entity_id=inc.id, ts=t)


def resolve(db: Session, inc: Incident, actor: str, note: str = "") -> None:
    _require_open(inc, "resolve it")
    close(db, inc, clock_now(), note=note or f"Resolved by {actor}", actor=actor)
    db.commit()


def _incident_jobs(db: Session, inc: Incident, kind: str) -> list[NotificationJob]:
    return list(db.scalars(select(NotificationJob).where(NotificationJob.incident_id == inc.id,
                                                         NotificationJob.kind == kind,
                                                         NotificationJob.status != "cancelled")))


def restoration_suggested(db: Session, inc: Incident) -> bool:
    """Restoration messages are optional; suggest one only when it is genuinely useful."""
    threshold = settings_store.get_section(db, "notifications").restoration_min_customers
    return (inc.verification_status == "confirmed" and inc.power_restored_at is not None
            and inc.estimated_customers >= threshold and not _incident_jobs(db, inc, "restoration"))


def announce_restoration(db: Session, inc: Incident, actor: str) -> NotificationJob:
    if inc.verification_status != "confirmed":
        raise conflict("restoration announcements are only available for confirmed outages")
    if inc.power_restored_at is None:
        raise conflict("power has not been restored for this incident yet")
    if _incident_jobs(db, inc, "restoration"):
        raise conflict("a restoration announcement was already sent for this incident")
    t = clock_now()
    job = notifications.create_job(db, kind="restoration", template_key="power_restored",
                                   area_ids=[inc.service_area_id], send_at=t, incident=inc, created_by=actor)
    _event(db, inc, "notification", f"Restoration announcement sent by {actor} to {job.recipients_count} customers",
           actor, t)
    db.commit()
    return notifications.send_job(db, job)


def send_update(db: Session, inc: Incident, actor: str, eta: str) -> NotificationJob:
    if not eta.strip():
        raise invalid("provide an estimated restoration time", "eta")
    if inc.verification_status != "confirmed":
        raise conflict("outage updates are only available for confirmed outages")
    if inc.power_restored_at is not None:
        raise conflict("power has already been restored")
    t = clock_now()
    job = notifications.create_job(db, kind="outage_update", template_key="extended_outage_update",
                                   area_ids=[inc.service_area_id], send_at=t, incident=inc, context={"eta": eta},
                                   created_by=actor)
    _event(db, inc, "notification", f"Extended outage update sent (ETA: {eta})", actor, t)
    db.commit()
    return notifications.send_job(db, job)
