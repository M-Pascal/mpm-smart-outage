"""Scheduled (planned) outages and unexpected-outage incidents."""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import serializers as S
from ..clock import iso, to_naive_utc
from ..clock import now as clock_now
from ..db import WRITE_LOCK
from ..errors import invalid, not_found, ok
from ..models import Incident, ScheduledOutage, ServiceArea
from ..services import incidents as incident_svc
from ..services import notifications, scheduled_outages
from ..services.notifications import REASON_LABELS
from .deps import actor, get_db

router = APIRouter(prefix="/api")

Reason = Literal["planned_maintenance", "equipment_replacement", "network_upgrade", "load_shedding",
                 "safety_inspection", "other"]
Priority = Literal["low", "medium", "high", "critical"]


class _Times(BaseModel):
    @field_validator("start_at", "end_at", mode="after", check_fields=False)
    @classmethod
    def _utc(cls, v: Optional[datetime]) -> Optional[datetime]:
        return to_naive_utc(v) if v else v

    @field_validator("reminder_offsets", mode="after", check_fields=False)
    @classmethod
    def _offsets(cls, v: Optional[list[int]]) -> Optional[list[int]]:
        if v is None:
            return v
        if any(o <= 0 for o in v):
            raise ValueError("advance notifications must be scheduled before the start time (offset > 0)")
        if any(o > 60 * 24 * 14 for o in v):
            raise ValueError("advance notifications can be at most 14 days before the start")
        return sorted(set(v), reverse=True)


class ScheduledOutageIn(_Times):
    title: str = Field(min_length=3, max_length=160)
    reason: Reason
    reason_detail: str = Field("", max_length=200)
    mini_grid_id: int
    service_area_ids: list[int] = Field(min_length=1)
    start_at: datetime
    end_at: datetime
    description: str = Field("", max_length=2000)
    priority: Priority = "medium"
    reminder_offsets: Optional[list[int]] = None
    send_notice_on_publish: bool = True
    publish: bool = False


class ScheduledOutagePatch(_Times):
    title: Optional[str] = Field(None, min_length=3, max_length=160)
    reason: Optional[Reason] = None
    reason_detail: Optional[str] = Field(None, max_length=200)
    mini_grid_id: Optional[int] = None
    service_area_ids: Optional[list[int]] = Field(None, min_length=1)
    start_at: Optional[datetime] = None
    end_at: Optional[datetime] = None
    description: Optional[str] = Field(None, max_length=2000)
    priority: Optional[Priority] = None
    reminder_offsets: Optional[list[int]] = None
    send_notice_on_publish: Optional[bool] = None
    notify_customers: bool = True


class PlanPreviewIn(_Times):
    title: str = ""
    reason: Reason = "planned_maintenance"
    reason_detail: str = ""
    mini_grid_id: Optional[int] = None
    service_area_ids: list[int] = Field(default_factory=list)
    start_at: datetime
    end_at: datetime
    reminder_offsets: list[int] = Field(default_factory=list)
    send_notice_on_publish: bool = True
    outage_id: Optional[int] = None


class CancelIn(BaseModel):
    reason: str = Field("", max_length=300)
    notify_customers: bool = True


def _outage(db: Session, outage_id: int) -> ScheduledOutage:
    o = db.get(ScheduledOutage, outage_id)
    if o is None:
        raise not_found("Scheduled outage", outage_id)
    return o


# ------------------------------------------------------ scheduled outages
@router.get("/outages")
def all_outages(db: Session = Depends(get_db)):
    planned = db.scalars(select(ScheduledOutage).order_by(ScheduledOutage.start_at.desc())).all()
    unexpected = db.scalars(select(Incident).where(Incident.verification_status != "rejected")
                            .order_by(Incident.detected_at.desc()).limit(100)).all()
    return ok({"planned": [S.scheduled_outage(o, db) for o in planned],
               "unexpected": [S.incident(i, db) for i in unexpected]})


@router.get("/outages/scheduled")
def list_scheduled(status: Optional[str] = None, q: Optional[str] = None, db: Session = Depends(get_db)):
    query = select(ScheduledOutage).order_by(ScheduledOutage.start_at)
    if status:
        query = query.where(ScheduledOutage.status.in_(status.split(",")))
    items = [S.scheduled_outage(o, db) for o in db.scalars(query)]
    if q:
        ql = q.lower()
        items = [i for i in items if ql in i["title"].lower() or ql in i["code"].lower()
                 or any(ql in a["name"].lower() for a in i["service_areas"])]
    return ok(items, reasons=REASON_LABELS)


@router.get("/outages/scheduled/{outage_id}")
def get_scheduled(outage_id: int, db: Session = Depends(get_db)):
    return ok(S.scheduled_outage(_outage(db, outage_id), db, jobs=True))


@router.post("/outages/scheduled", status_code=201)
def create_scheduled(body: ScheduledOutageIn, db: Session = Depends(get_db)):
    with WRITE_LOCK:
        data = body.model_dump(exclude={"publish"})
        outage = scheduled_outages.create(db, data, publish_now=body.publish, actor=actor(db))
        return ok(S.scheduled_outage(outage, db, jobs=True))


@router.post("/outages/scheduled/preview")
def preview_plan(body: PlanPreviewIn, db: Session = Depends(get_db)):
    """Exact send times + rendered messages for a draft or edited event (nothing is saved)."""
    t = clock_now()
    if body.end_at <= body.start_at:
        raise invalid("expected restoration must be after the start time", "end_at")
    existing = db.get(ScheduledOutage, body.outage_id) if body.outage_id else None
    published = existing is not None and existing.status not in ("draft",)
    plan = scheduled_outages.plan_notifications(body.start_at, body.reminder_offsets, body.send_notice_on_publish, t,
                                                published=published)
    preview_outage = ScheduledOutage(title=body.title or "Planned interruption", reason=body.reason,
                                     reason_detail=body.reason_detail, start_at=body.start_at, end_at=body.end_at)
    area_ids = body.service_area_ids
    messages = {}
    if area_ids:
        messages["notice"] = notifications.preview(db, template_key="scheduled_maintenance_notice", body=None,
                                                   area_ids=area_ids, outage=preview_outage, at=t)
        first_reminder = next((p for p in plan if p["kind"] == "reminder" and p["valid"]), None)
        if first_reminder:
            messages["reminder"] = notifications.preview(db, template_key="maintenance_reminder", body=None,
                                                         area_ids=area_ids, outage=preview_outage,
                                                         at=first_reminder["send_at"])
        if existing is not None and existing.customers_notified and body.start_at != existing.start_at:
            from ..services.timefmt import fmt_date, fmt_time
            tz = scheduled_outages._tz(db)
            messages["reschedule"] = notifications.preview(
                db, template_key="maintenance_rescheduled", body=None, area_ids=area_ids, outage=preview_outage, at=t,
                context={"old_date": fmt_date(existing.start_at, tz), "old_start_time": fmt_time(existing.start_at, tz),
                         "old_end_time": fmt_time(existing.end_at, tz)})
    recipients = notifications.audience(db, area_ids)
    return ok({
        "schedule": [{**p, "send_at": iso(p["send_at"])} for p in plan],
        "messages": messages,
        "recipients": {"eligible": len(recipients["eligible"]), "total_in_areas": len(recipients["customers"]),
                       "excluded": recipients["excluded"]},
        "start_in_past": body.start_at <= t,
        "simulated": True,
    })


@router.patch("/outages/scheduled/{outage_id}")
def update_scheduled(outage_id: int, body: ScheduledOutagePatch, db: Session = Depends(get_db)):
    with WRITE_LOCK:
        outage = _outage(db, outage_id)
        data = body.model_dump(exclude_unset=True, exclude={"notify_customers"})
        data = {k: v for k, v in data.items() if v is not None}
        changes = scheduled_outages.update(db, outage, data, notify_customers=body.notify_customers, actor=actor(db))
        return ok(S.scheduled_outage(outage, db, jobs=True), changes=changes)


@router.post("/outages/scheduled/{outage_id}/publish")
def publish_scheduled(outage_id: int, db: Session = Depends(get_db)):
    with WRITE_LOCK:
        outage = scheduled_outages.publish(db, _outage(db, outage_id), actor=actor(db))
        return ok(S.scheduled_outage(outage, db, jobs=True))


@router.post("/outages/scheduled/{outage_id}/cancel")
def cancel_scheduled(outage_id: int, body: CancelIn = CancelIn(), db: Session = Depends(get_db)):
    with WRITE_LOCK:
        outage = _outage(db, outage_id)
        result = scheduled_outages.cancel(db, outage, reason=body.reason, notify_customers=body.notify_customers,
                                          actor=actor(db))
        return ok(S.scheduled_outage(outage, db, jobs=True), changes=result)


# --------------------------------------------------------------- incidents
class NotifyIn(BaseModel):
    notify_customers: bool = True


class NoteIn(BaseModel):
    note: str = Field("", max_length=500)


class RejectIn(BaseModel):
    reason: str = Field("", max_length=300)


class UpdateIn(BaseModel):
    eta: str = Field(min_length=1, max_length=120)


def _incident(db: Session, incident_id: int) -> Incident:
    inc = db.get(Incident, incident_id)
    if inc is None:
        raise not_found("Incident", incident_id)
    return inc


@router.get("/incidents")
def list_incidents(status: Literal["active", "resolved", "all"] = "all", severity: Optional[str] = None,
                   area_id: Optional[int] = None, limit: int = Query(200, ge=1, le=500), db: Session = Depends(get_db)):
    q = select(Incident).order_by(Incident.detected_at.desc()).limit(limit)
    if status == "active":
        q = q.where(Incident.resolution_status != "resolved")
    elif status == "resolved":
        q = q.where(Incident.resolution_status == "resolved")
    if severity:
        q = q.where(Incident.severity.in_(severity.split(",")))
    if area_id:
        q = q.where(Incident.service_area_id == area_id)
    return ok([S.incident(i, db) for i in db.scalars(q)])


@router.get("/incidents/{incident_id}")
def get_incident(incident_id: int, db: Session = Depends(get_db)):
    return ok(S.incident(_incident(db, incident_id), db, detail=True))


def _after(db: Session, inc: Incident):
    db.refresh(inc)
    return ok(S.incident(inc, db, detail=True))


@router.post("/incidents/{incident_id}/acknowledge")
def ack_incident(incident_id: int, db: Session = Depends(get_db)):
    with WRITE_LOCK:
        inc = _incident(db, incident_id)
        incident_svc.acknowledge(db, inc, actor(db))
        return _after(db, inc)


@router.post("/incidents/{incident_id}/investigate")
def investigate_incident(incident_id: int, body: NoteIn = NoteIn(), db: Session = Depends(get_db)):
    with WRITE_LOCK:
        inc = _incident(db, incident_id)
        incident_svc.investigate(db, inc, actor(db), body.note)
        return _after(db, inc)


@router.post("/incidents/{incident_id}/confirm")
def confirm_incident(incident_id: int, body: NotifyIn = NotifyIn(), db: Session = Depends(get_db)):
    with WRITE_LOCK:
        inc = _incident(db, incident_id)
        incident_svc.confirm(db, inc, method="manual", actor=actor(db), notify_customers=body.notify_customers)
        return _after(db, inc)


@router.post("/incidents/{incident_id}/reject")
def reject_incident(incident_id: int, body: RejectIn = RejectIn(), db: Session = Depends(get_db)):
    with WRITE_LOCK:
        inc = _incident(db, incident_id)
        incident_svc.reject(db, inc, actor(db), body.reason)
        return _after(db, inc)


@router.post("/incidents/{incident_id}/resolve")
def resolve_incident(incident_id: int, body: NoteIn = NoteIn(), db: Session = Depends(get_db)):
    with WRITE_LOCK:
        inc = _incident(db, incident_id)
        incident_svc.resolve(db, inc, actor(db), body.note)
        return _after(db, inc)


@router.post("/incidents/{incident_id}/announce-restoration")
def announce_restoration(incident_id: int, db: Session = Depends(get_db)):
    with WRITE_LOCK:
        inc = _incident(db, incident_id)
        incident_svc.announce_restoration(db, inc, actor(db))
        return _after(db, inc)


@router.post("/incidents/{incident_id}/send-update")
def send_update(incident_id: int, body: UpdateIn, db: Session = Depends(get_db)):
    with WRITE_LOCK:
        inc = _incident(db, incident_id)
        incident_svc.send_update(db, inc, actor(db), body.eta)
        return _after(db, inc)


@router.get("/service-areas/{area_id}/planned")
def area_planned(area_id: int, db: Session = Depends(get_db)):
    area = db.get(ServiceArea, area_id)
    if area is None:
        raise not_found("Service area", area_id)
    items = [o for o in db.scalars(select(ScheduledOutage).order_by(ScheduledOutage.start_at)) if area in o.service_areas]
    return ok([S.scheduled_outage(o, db) for o in items])
