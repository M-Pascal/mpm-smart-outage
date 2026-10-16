"""Notifications, templates, WhatsApp Channel announcements and customers."""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from .. import serializers as S
from ..clock import to_naive_utc
from ..clock import now as clock_now
from ..db import WRITE_LOCK
from ..errors import conflict, invalid, not_found, ok
from ..models import Customer, Incident, Meter, NotificationJob, NotificationMessage, NotificationTemplate, ScheduledOutage, ServiceArea
from ..services import activity, notifications, settings_store
from ..services.templates import DEFAULT_TEMPLATES, PLACEHOLDERS, unknown_placeholders
from ..services.timefmt import fmt_date, fmt_time
from .deps import actor, get_db

router = APIRouter(prefix="/api")


# ----------------------------------------------------------- notifications
class PreviewIn(BaseModel):
    template_key: Optional[str] = None
    body: Optional[str] = Field(None, max_length=2000)
    area_ids: list[int] = Field(default_factory=list)
    context: dict[str, Any] = Field(default_factory=dict)
    scheduled_outage_id: Optional[int] = None
    incident_id: Optional[int] = None


class NotificationIn(BaseModel):
    template_key: str
    area_ids: list[int] = Field(min_length=1)
    context: dict[str, Any] = Field(default_factory=dict)
    mode: Literal["draft", "schedule", "send_now"] = "send_now"
    send_at: Optional[datetime] = None
    scheduled_outage_id: Optional[int] = None
    incident_id: Optional[int] = None

    @field_validator("send_at", mode="after")
    @classmethod
    def _utc(cls, v: Optional[datetime]) -> Optional[datetime]:
        return to_naive_utc(v) if v else v


class SimulateIn(BaseModel):
    job_id: int


class ScheduleIn(BaseModel):
    send_at: datetime

    @field_validator("send_at", mode="after")
    @classmethod
    def _utc(cls, v: datetime) -> datetime:
        return to_naive_utc(v)


def _links(db: Session, outage_id: Optional[int], incident_id: Optional[int]):
    outage = db.get(ScheduledOutage, outage_id) if outage_id else None
    incident = db.get(Incident, incident_id) if incident_id else None
    if outage_id and outage is None:
        raise not_found("Scheduled outage", outage_id)
    if incident_id and incident is None:
        raise not_found("Incident", incident_id)
    return outage, incident


def _job(db: Session, job_id: int) -> NotificationJob:
    job = db.get(NotificationJob, job_id)
    if job is None:
        raise not_found("Notification", job_id)
    return job


@router.get("/notifications")
def list_notifications(status: Optional[str] = None, kind: Optional[str] = None, q: Optional[str] = None,
                       limit: int = Query(300, ge=1, le=1000), db: Session = Depends(get_db)):
    query = select(NotificationJob).order_by(NotificationJob.send_at.desc()).limit(limit)
    if status:
        query = query.where(NotificationJob.status.in_(status.split(",")))
    if kind:
        query = query.where(NotificationJob.kind.in_(kind.split(",")))
    items = [S.job(j) for j in db.scalars(query)]
    if q:
        ql = q.lower()
        items = [i for i in items if ql in i["kind_label"].lower() or ql in i["code"].lower()
                 or (i["linked"] and (ql in i["linked"]["title"].lower() or ql in i["linked"]["code"].lower()))]
    return ok(items)


@router.get("/notifications/messages")
def list_messages(status: Optional[str] = None, q: Optional[str] = None, limit: int = Query(200, ge=1, le=1000),
                  db: Session = Depends(get_db)):
    query = (select(NotificationMessage).options(selectinload(NotificationMessage.customer))
             .order_by(NotificationMessage.created_at.desc(), NotificationMessage.id.desc()).limit(limit))
    if status:
        query = query.where(NotificationMessage.status == status)
    items = [S.message(m) for m in db.scalars(query)]
    if q:
        ql = q.lower()
        items = [i for i in items if ql in i["customer_name"].lower() or ql in i["service_area_name"].lower()]
    return ok(items)


@router.get("/notifications/{job_id}")
def get_notification(job_id: int, db: Session = Depends(get_db)):
    job = _job(db, job_id)
    data = S.job(job)
    data["messages"] = [{**S.message(m), "delivery_attempts": [S.delivery_attempt(a) for a in m.delivery_attempts]}
                        for m in sorted(job.messages, key=lambda m: m.id)]
    data["preview"] = notifications.render_job(db, job) if job.status in ("draft", "scheduled") else None
    return ok(data)


@router.post("/notifications/preview")
def preview_notification(body: PreviewIn, db: Session = Depends(get_db)):
    outage, incident = _links(db, body.scheduled_outage_id, body.incident_id)
    area_ids = body.area_ids or ([a.id for a in outage.service_areas] if outage else
                                 [incident.service_area_id] if incident else [])
    if body.body and (bad := unknown_placeholders(body.body)):
        raise invalid(f"unknown placeholder(s): {', '.join('{' + b + '}' for b in bad)}", "body")
    return ok(notifications.preview(db, template_key=body.template_key, body=body.body, area_ids=area_ids,
                                    context=body.context, outage=outage, incident=incident))


@router.post("/notifications", status_code=201)
def create_notification(body: NotificationIn, db: Session = Depends(get_db)):
    with WRITE_LOCK:
        outage, incident = _links(db, body.scheduled_outage_id, body.incident_id)
        if body.mode == "schedule":
            if body.send_at is None:
                raise invalid("choose when the notification should be sent", "send_at")
            if body.send_at <= clock_now():
                raise invalid("the send time must be in the future", "send_at")
        if outage is not None and body.send_at and body.mode == "schedule" and body.send_at >= outage.start_at \
                and body.template_key in ("scheduled_maintenance_notice", "maintenance_reminder"):
            raise invalid("an advance warning must be sent before the interruption starts", "send_at")
        if db.scalars(select(ServiceArea.id).where(ServiceArea.id.in_(body.area_ids))).all().__len__() != len(set(body.area_ids)):
            raise invalid("one or more service areas do not exist", "area_ids")
        send_at = body.send_at if body.mode == "schedule" else clock_now()
        job = notifications.create_job(db, kind="manual", template_key=body.template_key, area_ids=body.area_ids,
                                       send_at=send_at, status="draft" if body.mode == "draft" else "scheduled",
                                       outage=outage, incident=incident, context=body.context, created_by=actor(db))
        db.commit()
        if body.mode == "send_now":
            notifications.send_job(db, job)
        return ok(S.job(job))


@router.post("/notifications/simulate")
def simulate_send(body: SimulateIn, db: Session = Depends(get_db)):
    """Send a draft or scheduled notification immediately through the simulator."""
    with WRITE_LOCK:
        job = notifications.send_job(db, _job(db, body.job_id))
        return ok(S.job(job))


@router.post("/notifications/{job_id}/schedule")
def schedule_draft(job_id: int, body: ScheduleIn, db: Session = Depends(get_db)):
    with WRITE_LOCK:
        job = _job(db, job_id)
        if job.status not in ("draft", "scheduled"):
            raise conflict(f"notification is {job.status}")
        if body.send_at <= clock_now():
            raise invalid("the send time must be in the future", "send_at")
        job.send_at, job.status = body.send_at, "scheduled"
        db.commit()
        return ok(S.job(job))


@router.post("/notifications/{job_id}/cancel")
def cancel_notification(job_id: int, db: Session = Depends(get_db)):
    with WRITE_LOCK:
        job = _job(db, job_id)
        notifications.cancel_job(db, job, f"Cancelled by {actor(db)}")
        activity.log(db, "notification_cancelled", f"Notification NTF-{job.id:04d} cancelled", severity="warning",
                     entity_type="notification", entity_id=job.id)
        db.commit()
        return ok(S.job(job))


@router.post("/notifications/{job_id}/retry")
def retry_notification(job_id: int, db: Session = Depends(get_db)):
    with WRITE_LOCK:
        return ok(S.job(notifications.retry_failed(db, _job(db, job_id))))


# --------------------------------------------------------------- templates
class TemplateIn(BaseModel):
    body: str = Field(min_length=10, max_length=2000)
    name: Optional[str] = Field(None, min_length=3, max_length=120)


@router.get("/templates")
def list_templates(db: Session = Depends(get_db)):
    return ok([S.template(t) for t in db.scalars(select(NotificationTemplate).order_by(NotificationTemplate.id))],
              placeholders=PLACEHOLDERS)


@router.get("/templates/{key}/whatsapp")
def template_whatsapp_definition(key: str, request: Request, db: Session = Depends(get_db)):
    """Template text to submit in WhatsApp Manager, with PowerChat placeholders mapped to {{1}}, {{2}}, ..."""
    tpl = db.scalar(select(NotificationTemplate).where(NotificationTemplate.key == key))
    if tpl is None:
        raise not_found("Template", key)
    definition = notifications.whatsapp_definition(tpl.body)
    return ok({"name": tpl.key, "language": request.app.state.config.whatsapp_template_language,
               "category": "UTILITY", **definition})


@router.put("/templates/{key}")
def update_template(key: str, body: TemplateIn, db: Session = Depends(get_db)):
    with WRITE_LOCK:
        tpl = db.scalar(select(NotificationTemplate).where(NotificationTemplate.key == key))
        if tpl is None:
            raise not_found("Template", key)
        if bad := unknown_placeholders(body.body):
            raise invalid(f"unknown placeholder(s): {', '.join('{' + b + '}' for b in bad)}", "body")
        tpl.body = body.body
        if body.name:
            tpl.name = body.name
        activity.log(db, "template_updated", f"Message template “{tpl.name}” updated", entity_type="template",
                     entity_id=tpl.id)
        db.commit()
        return ok(S.template(tpl))


@router.post("/templates/{key}/reset")
def reset_template(key: str, db: Session = Depends(get_db)):
    with WRITE_LOCK:
        tpl = db.scalar(select(NotificationTemplate).where(NotificationTemplate.key == key))
        default = next((t for t in DEFAULT_TEMPLATES if t["key"] == key), None)
        if tpl is None or default is None:
            raise not_found("Template", key)
        tpl.body, tpl.name = default["body"], default["name"]
        db.commit()
        return ok(S.template(tpl))


# ------------------------------------------------------ WhatsApp Channels
class ChannelIn(BaseModel):
    scheduled_outage_id: Optional[int] = None
    incident_id: Optional[int] = None
    custom_text: Optional[str] = Field(None, max_length=1500)


_PHONE = re.compile(r"\+?\d[\d\s-]{7,}\d")


@router.post("/channels/announcement")
def channel_announcement(body: ChannelIn, db: Session = Depends(get_db)):
    """Channel-ready public text. No customer names or numbers are ever included."""
    org = settings_store.get_section(db, "general").organization_name
    tz = settings_store.get_section(db, "general").timezone
    outage, incident = _links(db, body.scheduled_outage_id, body.incident_id)
    if outage is not None:
        areas = ", ".join(a.name for a in outage.service_areas)
        reason = outage.reason_detail or notifications.REASON_LABELS.get(outage.reason, outage.reason)
        if outage.status == "cancelled":
            text = (f"📢 *{org}: Planned interruption cancelled*\n\nThe interruption planned for {areas} on "
                    f"{fmt_date(outage.start_at, tz)} ({fmt_time(outage.start_at, tz)}–{fmt_time(outage.end_at, tz)}) "
                    f"has been cancelled. Supply continues as normal.")
        else:
            text = (f"⚡ *{org}: Planned power interruption*\n\n📍 Areas: {areas}\n📅 Date: {fmt_date(outage.start_at, tz)}\n"
                    f"🕘 Time: {fmt_time(outage.start_at, tz)} – {fmt_time(outage.end_at, tz)}\n🔧 Reason: {reason}\n\n"
                    "Please plan accordingly. We apologise for the inconvenience.")
    elif incident is not None:
        if incident.power_restored_at:
            text = (f"✅ *{org}: Power restored*\n\nElectricity supply in {incident.service_area.name} has been restored. "
                    "Thank you for your patience.")
        else:
            text = (f"⚠️ *{org}: Unexpected power interruption*\n\nWe are aware of an electricity interruption in "
                    f"{incident.service_area.name}. Our technical team is investigating. Updates will follow when "
                    "reliable information is available.")
    elif body.custom_text:
        if _PHONE.search(body.custom_text):
            raise invalid("public announcements must not contain phone numbers", "custom_text")
        text = f"📢 *{org}*\n\n{body.custom_text.strip()}"
    else:
        raise invalid("choose an event or enter announcement text", "scheduled_outage_id")
    return ok({"text": text, "publish": "manual",
               "note": "WhatsApp Channels have no documented publishing API. Copy this text and post it manually."})


# --------------------------------------------------------------- customers
PHONE_RE = r"^\+[1-9]\d{7,14}$"


class CustomerIn(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    phone: str = Field(pattern=PHONE_RE, description="E.164 format, e.g. +250700100001")
    service_area_id: int
    customer_type: Literal["residential", "commercial", "productive_use", "public_institution", "essential_service"] = "residential"
    notification_preference: Literal["whatsapp", "sms", "none"] = "whatsapp"
    whatsapp_opt_in: bool = False
    account_status: Literal["active", "suspended", "inactive"] = "active"
    notes: str = Field("", max_length=1000)
    create_meter: bool = False


class CustomerPatch(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=160)
    phone: Optional[str] = Field(None, pattern=PHONE_RE)
    service_area_id: Optional[int] = None
    customer_type: Optional[Literal["residential", "commercial", "productive_use", "public_institution", "essential_service"]] = None
    notification_preference: Optional[Literal["whatsapp", "sms", "none"]] = None
    whatsapp_opt_in: Optional[bool] = None
    account_status: Optional[Literal["active", "suspended", "inactive"]] = None
    notes: Optional[str] = Field(None, max_length=1000)


def _customer(db: Session, customer_id: int) -> Customer:
    c = db.get(Customer, customer_id)
    if c is None:
        raise not_found("Customer", customer_id)
    return c


@router.get("/customers")
def list_customers(q: Optional[str] = None, area_id: Optional[int] = None, status: Optional[str] = None,
                   opt_in: Optional[bool] = None, preference: Optional[str] = None, db: Session = Depends(get_db)):
    query = select(Customer).options(selectinload(Customer.service_area), selectinload(Customer.meter)).order_by(Customer.id)
    if q:
        like = f"%{q}%"
        query = query.outerjoin(Meter, Meter.customer_id == Customer.id).where(
            or_(Customer.name.ilike(like), Customer.phone.ilike(like), Meter.serial.ilike(like)))
    if area_id:
        query = query.where(Customer.service_area_id == area_id)
    if status:
        query = query.where(Customer.account_status == status)
    if opt_in is not None:
        query = query.where(Customer.whatsapp_opt_in.is_(opt_in))
    if preference:
        query = query.where(Customer.notification_preference == preference)
    items = [S.customer(c) for c in db.scalars(query)]
    if q and q.upper().startswith("CUS-"):
        items = [S.customer(c) for c in db.scalars(select(Customer)) if f"CUS-{c.id:04d}" == q.upper()] or items
    return ok(items)


@router.get("/customers/{customer_id}")
def get_customer(customer_id: int, db: Session = Depends(get_db)):
    c = _customer(db, customer_id)
    data = S.customer(c)
    msgs = db.scalars(select(NotificationMessage).where(NotificationMessage.customer_id == c.id)
                      .order_by(NotificationMessage.created_at.desc()).limit(20)).all()
    data["recent_messages"] = [S.message(m) for m in msgs]
    return ok(data)


@router.post("/customers", status_code=201)
def create_customer(body: CustomerIn, db: Session = Depends(get_db)):
    with WRITE_LOCK:
        area = db.get(ServiceArea, body.service_area_id)
        if area is None:
            raise invalid("select a valid service area", "service_area_id")
        if db.scalar(select(Customer).where(Customer.phone == body.phone)):
            raise invalid("another customer already uses this phone number", "phone")
        c = Customer(**body.model_dump(exclude={"create_meter"}))
        db.add(c)
        db.flush()
        if body.create_meter:
            db.add(Meter(serial=f"PC-{area.code}{c.id:03d}", service_area_id=area.id, customer_id=c.id,
                         status="normal", status_since=clock_now()))
        activity.log(db, "customer_added", f"Customer {c.name} added to {area.name}", entity_type="customer",
                     entity_id=c.id)
        db.commit()
        db.refresh(c)
        return ok(S.customer(c))


@router.patch("/customers/{customer_id}")
def update_customer(customer_id: int, body: CustomerPatch, db: Session = Depends(get_db)):
    with WRITE_LOCK:
        c = _customer(db, customer_id)
        data = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None}
        if c.source == "mpm":
            managed = [f for f in ("name", "phone", "service_area_id") if f in data and data[f] != getattr(c, f)]
            if managed:
                raise conflict(f"{', '.join(managed)} of this customer is managed in MicroPowerManager; edit it there")
        if "service_area_id" in data and db.get(ServiceArea, data["service_area_id"]) is None:
            raise invalid("select a valid service area", "service_area_id")
        if "phone" in data and db.scalar(select(Customer).where(Customer.phone == data["phone"], Customer.id != c.id)):
            raise invalid("another customer already uses this phone number", "phone")
        consent_changed = "whatsapp_opt_in" in data and data["whatsapp_opt_in"] != c.whatsapp_opt_in
        for k, v in data.items():
            setattr(c, k, v)
        if c.meter and "service_area_id" in data:
            c.meter.service_area_id = data["service_area_id"]
        if consent_changed:
            c.consent_source, c.consent_updated_at = "operator", clock_now()
            activity.log(db, "consent_changed", f"WhatsApp consent {'granted' if c.whatsapp_opt_in else 'withdrawn'} "
                         f"for {c.name}", entity_type="customer", entity_id=c.id)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise invalid("could not save customer (duplicate value)")
        db.refresh(c)
        return ok(S.customer(c))
