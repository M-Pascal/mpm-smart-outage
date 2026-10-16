"""Notification jobs: recipients, rendering, simulated sending, retries.

Duplicate-send protection:
  1. A job is *claimed* with a conditional UPDATE (status scheduled -> processing);
     only one worker can win the claim.
  2. notification_messages has UNIQUE(job_id, customer_id) and the sender skips
     customers that already have a message for the job, so a job interrupted
     mid-send (e.g. by a restart) can be resumed safely.
"""
from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..clock import now as clock_now
from ..errors import conflict, invalid, not_found
from ..models import Customer, Incident, NotificationJob, NotificationMessage, NotificationTemplate, ScheduledOutage, ServiceArea
from . import activity, settings_store
from .templates import TEMPLATE_KEYS, missing_placeholders, render
from .timefmt import fmt_date, fmt_minutes, fmt_time

REASON_LABELS = {
    "planned_maintenance": "planned maintenance",
    "equipment_replacement": "equipment replacement",
    "network_upgrade": "a network upgrade",
    "load_shedding": "planned load shedding",
    "safety_inspection": "a safety inspection",
    "other": "technical works",
}

KIND_LABELS = {
    "notice": "Maintenance notice",
    "reminder": "Maintenance reminder",
    "reschedule": "Rescheduling notice",
    "cancellation": "Cancellation notice",
    "outage_alert": "Unexpected outage alert",
    "outage_update": "Extended outage update",
    "restoration": "Restoration announcement",
    "manual": "Manual announcement",
}

ADVANCE_KINDS = {"notice", "reminder"}
PENDING = ("draft", "scheduled")

_SIM_FAILURES = [
    "Simulated: recipient number is not registered on WhatsApp",
    "Simulated: message undeliverable (phone unreachable)",
    "Simulated: provider rate limit reached",
]


# -------------------------------------------------------------- recipients
def eligibility(customer: Customer) -> str | None:
    """None if the customer may receive WhatsApp messages, else the reason they are excluded."""
    if customer.account_status != "active":
        return f"account {customer.account_status}"
    if not customer.whatsapp_opt_in:
        return "no WhatsApp consent"
    if customer.notification_preference != "whatsapp":
        return f"prefers {customer.notification_preference}"
    return None


def audience(db: Session, area_ids: list[int]) -> dict[str, Any]:
    customers = db.scalars(select(Customer).where(Customer.service_area_id.in_(area_ids or [-1]))).all()
    eligible, excluded = [], {}
    for c in customers:
        reason = eligibility(c)
        if reason is None:
            eligible.append(c)
        else:
            excluded[reason] = excluded.get(reason, 0) + 1
    return {"customers": customers, "eligible": eligible, "excluded": excluded}


# --------------------------------------------------------------- rendering
def build_context(db: Session, *, area_ids: list[int], context: dict[str, Any] | None = None,
                  outage: ScheduledOutage | None = None, incident: Incident | None = None,
                  customer: Customer | None = None, at: datetime | None = None) -> dict[str, Any]:
    general = settings_store.get_section(db, "general")
    tz = general.timezone
    at = at or clock_now()
    ctx: dict[str, Any] = {"organization": general.organization_name}
    if customer is not None:
        ctx["area"] = customer.service_area.name
        ctx["customer_name"] = customer.name
    else:
        areas = db.scalars(select(ServiceArea).where(ServiceArea.id.in_(area_ids or [-1])).order_by(ServiceArea.code)).all()
        ctx["area"] = ", ".join(a.name for a in areas) or "your area"
    if outage is not None:
        ctx.update(
            title=outage.title,
            reason=outage.reason_detail or REASON_LABELS.get(outage.reason, outage.reason),
            date=fmt_date(outage.start_at, tz),
            start_time=fmt_time(outage.start_at, tz),
            end_time=fmt_time(outage.end_at, tz),
            end_date=fmt_date(outage.end_at, tz),
        )
        if outage.start_at > at:
            ctx["time_until"] = fmt_minutes((outage.start_at - at).total_seconds() / 60)
    if incident is not None:
        ctx.setdefault("area", incident.service_area.name)
        ctx["detected_time"] = fmt_time(incident.detected_at, tz)
    ctx.update({k: v for k, v in (context or {}).items() if v not in (None, "")})
    return ctx


def template_body(db: Session, key: str) -> str:
    tpl = db.scalar(select(NotificationTemplate).where(NotificationTemplate.key == key))
    if tpl is None:
        raise not_found("Template", key)
    return tpl.body


def render_job(db: Session, job: NotificationJob, customer: Customer | None = None, at: datetime | None = None) -> str:
    ctx = build_context(db, area_ids=job.area_ids, context=job.context, outage=job.scheduled_outage,
                        incident=job.incident, customer=customer, at=at or job.send_at)
    return render(template_body(db, job.template_key), ctx)


# ---------------------------------------------------------------- creating
def create_job(db: Session, *, kind: str, template_key: str, area_ids: list[int], send_at: datetime,
               status: str = "scheduled", outage: ScheduledOutage | None = None, incident: Incident | None = None,
               context: dict[str, Any] | None = None, offset_minutes: int | None = None, note: str = "",
               created_by: str = "system") -> NotificationJob:
    if template_key not in TEMPLATE_KEYS:
        raise invalid(f"unknown template '{template_key}'", "template_key")
    if not area_ids:
        raise invalid("select at least one service area", "area_ids")
    if status not in ("draft", "scheduled"):
        raise invalid("new notifications must be draft or scheduled", "status")
    job = NotificationJob(kind=kind, template_key=template_key, area_ids=sorted(set(area_ids)), send_at=send_at,
                          status=status, scheduled_outage=outage, incident=incident, context=context or {},
                          offset_minutes=offset_minutes, note=note, created_by=created_by, created_at=clock_now())
    job.recipients_count = len(audience(db, job.area_ids)["eligible"])
    db.add(job)
    db.flush()
    verb = "drafted" if status == "draft" else ("queued" if send_at <= clock_now() else "scheduled")
    activity.log(db, "notification_queued", f"{KIND_LABELS.get(kind, kind)} {verb} for {job.recipients_count} customers",
                 entity_type="notification", entity_id=job.id)
    return job


def cancel_job(db: Session, job: NotificationJob, reason: str) -> None:
    if job.status not in PENDING:
        raise conflict(f"notification {job.id} is already {job.status} and cannot be cancelled")
    job.status = "cancelled"
    job.note = reason
    job.processed_at = clock_now()


# ----------------------------------------------------------------- sending
def _simulated_outcome(job_id: int, customer_id: int, attempt: int, failure_rate: float) -> tuple[bool, str]:
    """Deterministic pseudo-random delivery outcome (reproducible in tests and demos)."""
    h = int(hashlib.sha1(f"{job_id}:{customer_id}:{attempt}".encode()).hexdigest(), 16)
    if (h % 1000) < failure_rate * 1000:
        return False, _SIM_FAILURES[h % len(_SIM_FAILURES)]
    return True, ""


def _claim(db: Session, job_id: int, from_statuses: tuple[str, ...]) -> bool:
    result = db.execute(
        update(NotificationJob)
        .where(NotificationJob.id == job_id, NotificationJob.status.in_(from_statuses))
        .values(status="processing")
    )
    db.commit()
    return result.rowcount == 1


def send_job(db: Session, job: NotificationJob, *, claimed: bool = False) -> NotificationJob:
    """Send (simulate) a job now. Safe to call twice: the claim and the unique constraint prevent duplicates."""
    if not claimed and not _claim(db, job.id, PENDING):
        db.refresh(job)
        raise conflict(f"notification {job.id} is {job.status}; it can no longer be sent")
    db.refresh(job)
    t = clock_now()
    outage = job.scheduled_outage

    if outage is not None and job.kind in ADVANCE_KINDS and (outage.status == "cancelled" or t >= outage.start_at):
        job.status, job.processed_at = "cancelled", t
        job.note = "Skipped: an advance warning is never sent after the interruption has started"
        db.commit()
        return job

    rate = settings_store.get_section(db, "notifications").simulated_failure_rate
    already = set(db.scalars(select(NotificationMessage.customer_id).where(NotificationMessage.job_id == job.id)))
    eligible = audience(db, job.area_ids)["eligible"]
    for customer in eligible:
        if customer.id in already:
            continue
        success, error = _simulated_outcome(job.id, customer.id, 1, rate)
        db.add(NotificationMessage(
            job_id=job.id, customer_id=customer.id, phone=customer.phone,
            body=render_job(db, job, customer, at=t), status="simulated_sent" if success else "failed",
            error=error, simulated_message_id=f"sim-{job.id}-{customer.id}-1" if success else "", created_at=t,
        ))
    db.flush()
    _recount(db, job)
    job.processed_at = t
    job.status = "failed" if job.recipients_count and not job.sent_count else "simulated_sent"
    if not job.recipients_count:
        job.note = "No eligible recipients (consent, preference or account status)"
    if outage is not None and job.sent_count:
        outage.customers_notified = True
    sev = "warning" if job.failed_count else "success"
    activity.log(db, "notification_sent",
                 f"{KIND_LABELS.get(job.kind, job.kind)} sent in simulation to {job.sent_count} customers"
                 + (f" ({job.failed_count} failed)" if job.failed_count else ""),
                 severity=sev, entity_type="notification", entity_id=job.id)
    db.commit()
    return job


def _recount(db: Session, job: NotificationJob) -> None:
    msgs = db.scalars(select(NotificationMessage).where(NotificationMessage.job_id == job.id)).all()
    job.recipients_count = len(msgs)
    job.sent_count = sum(1 for m in msgs if m.status == "simulated_sent")
    job.failed_count = sum(1 for m in msgs if m.status == "failed")


def retry_failed(db: Session, job: NotificationJob) -> NotificationJob:
    if job.status not in ("simulated_sent", "failed") or not job.failed_count:
        raise conflict("this notification has no failed messages to retry")
    rate = settings_store.get_section(db, "notifications").simulated_failure_rate
    t = clock_now()
    for msg in db.scalars(select(NotificationMessage).where(NotificationMessage.job_id == job.id,
                                                            NotificationMessage.status == "failed")):
        msg.attempts += 1
        success, error = _simulated_outcome(job.id, msg.customer_id, msg.attempts, rate)
        msg.status, msg.error, msg.updated_at = ("simulated_sent" if success else "failed"), error, t
        if success:
            msg.simulated_message_id = f"sim-{job.id}-{msg.customer_id}-{msg.attempts}"
    db.flush()
    _recount(db, job)
    job.status = "failed" if not job.sent_count else "simulated_sent"
    activity.log(db, "notification_retry", f"Retried failed messages for notification #{job.id}: "
                 f"{job.sent_count} sent, {job.failed_count} still failing",
                 severity="warning" if job.failed_count else "success", entity_type="notification", entity_id=job.id)
    db.commit()
    return job


def process_due(db: Session, at: datetime | None = None) -> int:
    """Called by the scheduler: send every scheduled job whose time has come."""
    at = at or clock_now()
    due_ids = db.scalars(select(NotificationJob.id).where(NotificationJob.status == "scheduled",
                                                          NotificationJob.send_at <= at)
                         .order_by(NotificationJob.send_at)).all()
    # Jobs left in 'processing' (e.g. crash mid-send) are resumed; duplicates are impossible.
    stuck = db.scalars(select(NotificationJob.id).where(NotificationJob.status == "processing")).all()
    sent = 0
    for job_id in stuck:
        send_job(db, db.get(NotificationJob, job_id), claimed=True)
        sent += 1
    for job_id in due_ids:
        if _claim(db, job_id, ("scheduled",)):
            send_job(db, db.get(NotificationJob, job_id), claimed=True)
            sent += 1
    return sent


def preview(db: Session, *, template_key: str | None, body: str | None, area_ids: list[int],
            context: dict[str, Any] | None = None, outage: ScheduledOutage | None = None,
            incident: Incident | None = None, at: datetime | None = None) -> dict[str, Any]:
    if not body:
        if not template_key:
            raise invalid("provide template_key or body", "template_key")
        body = template_body(db, template_key)
    aud = audience(db, area_ids)
    ctx = build_context(db, area_ids=area_ids, context=context, outage=outage, incident=incident, at=at)
    sample_customer = aud["eligible"][0] if aud["eligible"] else None
    rendered = render(body, ctx if sample_customer is None else
                      build_context(db, area_ids=area_ids, context=context, outage=outage, incident=incident,
                                    customer=sample_customer, at=at))
    return {
        "body": rendered,
        "missing_placeholders": missing_placeholders(rendered),
        "recipients": {
            "eligible": len(aud["eligible"]),
            "total_in_areas": len(aud["customers"]),
            "excluded": aud["excluded"],
        },
        "simulated": True,
    }
