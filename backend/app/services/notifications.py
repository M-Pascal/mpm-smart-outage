"""Notification jobs: recipients, rendering, channel delivery, retries and delivery tracking.

A job is one communication (e.g. "24-hour reminder for PO-0007") to one or more service areas. Sending a job
creates one NotificationMessage per targeted customer, then delivers each message through the channel chosen
by app/channels/router.py (WhatsApp mock, WhatsApp Cloud API, or SMS via MicroPowerManager).

Duplicate-send protection:
  1. Jobs are claimed with a conditional UPDATE (scheduled -> processing); only one worker wins.
  2. UNIQUE(job_id, customer_id): a customer gets at most one message per job, even if a job is resumed.
  3. Each message is claimed (queued/retry_scheduled -> sending) before the provider call, and a message
     that already has a provider_message_id is never sent again.
  4. An outcome that may have reached the provider ("unknown", or a crash while "sending") is never retried
     automatically; an operator decides.
"""
from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from ..channels.base import OutboundMessage, SendResult
from ..channels.router import get_router
from ..clock import now as clock_now
from ..config import Config
from ..errors import conflict, invalid, not_found
from ..models import (
    Customer, DeliveryAttempt, Incident, NotificationJob, NotificationMessage, NotificationTemplate, ScheduledOutage,
    ServiceArea,
)
from ..phone import mask
from . import activity, settings_store
from .templates import TEMPLATE_KEYS, missing_placeholders, render
from .timefmt import fmt_date, fmt_minutes, fmt_time

log = logging.getLogger("powerchat.notifications")

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
ACCEPTED = ("sent", "delivered", "read")
IN_FLIGHT = ("queued", "sending", "retry_scheduled")
STATUS_RANK = {"queued": 0, "sending": 0, "retry_scheduled": 0, "sent": 1, "delivered": 2, "read": 3}
MAX_ATTEMPTS = 3
RETRY_BASE_SECONDS = 30
STUCK_SENDING = timedelta(minutes=5)
_PLACEHOLDER = re.compile(r"\{([a-z_]+)\}")


# -------------------------------------------------------------- recipients
def eligibility(customer: Customer) -> str | None:
    """None if the customer is targeted by notifications, else why they are excluded."""
    return get_router().excluded_reason(customer)


def audience(db: Session, area_ids: list[int]) -> dict[str, Any]:
    customers = db.scalars(select(Customer).where(Customer.service_area_id.in_(area_ids or [-1]))
                           .order_by(Customer.name)).all()
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


def template_parameters(body: str) -> list[str]:
    """Placeholder names in first-appearance order; they become WhatsApp template parameters {{1}}, {{2}}, ..."""
    seen: list[str] = []
    for name in _PLACEHOLDER.findall(body):
        if name not in seen:
            seen.append(name)
    return seen


def whatsapp_definition(body: str) -> dict[str, Any]:
    """The text to register in WhatsApp Manager: placeholders replaced by positional {{n}} variables."""
    names = template_parameters(body)
    numbered = _PLACEHOLDER.sub(lambda m: "{{" + str(names.index(m.group(1)) + 1) + "}}", body)
    return {"body": numbered, "parameters": [{"position": i + 1, "name": n} for i, n in enumerate(names)]}


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
def _claim_job(db: Session, job_id: int, from_statuses: tuple[str, ...]) -> bool:
    result = db.execute(update(NotificationJob)
                        .where(NotificationJob.id == job_id, NotificationJob.status.in_(from_statuses))
                        .values(status="processing"))
    db.commit()
    return result.rowcount == 1


def _claim_message(db: Session, message_id: int, t: datetime) -> bool:
    result = db.execute(update(NotificationMessage)
                        .where(NotificationMessage.id == message_id,
                               NotificationMessage.status.in_(("queued", "retry_scheduled")),
                               NotificationMessage.provider_message_id.is_(None))
                        .values(status="sending", updated_at=t))
    db.commit()
    return result.rowcount == 1


def send_job(db: Session, job: NotificationJob, *, claimed: bool = False) -> NotificationJob:
    """Create per-recipient messages for a job and deliver them. Safe to call twice."""
    if not claimed and not _claim_job(db, job.id, PENDING):
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

    router = get_router()
    router.failure_rate = settings_store.get_section(db, "notifications").simulated_failure_rate
    already = set(db.scalars(select(NotificationMessage.customer_id).where(NotificationMessage.job_id == job.id)))
    for customer in audience(db, job.area_ids)["eligible"]:
        if customer.id in already:
            continue
        route = router.route(customer)
        message = NotificationMessage(
            job_id=job.id, customer_id=customer.id, phone=customer.phone, body=render_job(db, job, customer, at=t),
            status="queued", channel=route.channel.channel, provider=route.channel.provider,
            simulated=route.channel.simulated, attempts=0, created_at=t, updated_at=t,
        )
        if route.blocked_reason:
            message.status, message.failed_at = "failed", t
            message.error_code, message.error = route.blocked_code, route.blocked_reason
        db.add(message)
    db.commit()

    for message_id in db.scalars(select(NotificationMessage.id).where(NotificationMessage.job_id == job.id,
                                                                       NotificationMessage.status == "queued")).all():
        deliver(db, db.get(NotificationMessage, message_id))

    db.refresh(job)
    _finalise_job(db, job, t)
    sent, failed = job.sent_count, job.failed_count
    activity.log(db, "notification_sent",
                 f"{KIND_LABELS.get(job.kind, job.kind)} {'sent in simulation' if job.simulated else 'sent'} to "
                 f"{sent} customers" + (f" ({failed} failed)" if failed else ""),
                 severity="warning" if failed else "success", entity_type="notification", entity_id=job.id)
    db.commit()
    return job


def deliver(db: Session, message: NotificationMessage) -> NotificationMessage:
    """One delivery attempt for one message, through the channel it was routed to."""
    t = clock_now()
    if not _claim_message(db, message.id, t):
        db.refresh(message)
        return message
    db.refresh(message)
    job = message.job
    customer = message.customer
    router = get_router()
    route = router.route(customer)
    channel = route.channel
    if channel is None or channel.provider != message.provider:
        # Consent was withdrawn or configuration changed since the message was queued: never send it.
        return _fail(db, message, t, "not_eligible", route.excluded_reason or route.blocked_reason or
                     "Recipient routing changed since the message was queued")
    if route.blocked_reason:
        return _fail(db, message, t, route.blocked_code, route.blocked_reason)

    body = template_body(db, job.template_key)
    ctx = build_context(db, area_ids=job.area_ids, context=job.context, outage=job.scheduled_outage,
                        incident=job.incident, customer=customer, at=job.processed_at or t)
    attempt_no = message.attempts + 1
    outbound = OutboundMessage(
        to=customer.phone, template=job.template_key, language=router.config.whatsapp_template_language,
        parameters=[str(ctx.get(name, "")) for name in template_parameters(body)], body=message.body,
        reference=f"{job.id}-{customer.id}", attempt=attempt_no,
    )
    result = channel.send(outbound)
    _record_attempt(db, message, attempt_no, channel.provider, t, result)
    message.attempts = attempt_no
    if result.outcome == "accepted":
        message.status, message.sent_at = "sent", t
        message.provider_message_id = result.provider_message_id
        message.error_code, message.error, message.next_retry_at = "", "", None
    elif result.outcome == "retryable_error" and attempt_no < MAX_ATTEMPTS:
        delay = result.retry_after_seconds or RETRY_BASE_SECONDS * (2 ** (attempt_no - 1))
        message.status, message.next_retry_at = "retry_scheduled", t + timedelta(seconds=delay)
        message.error_code, message.error = result.error_code, result.error_message
    else:
        return _fail(db, message, t, result.error_code, result.error_message, commit=True)
    message.updated_at = t
    log.info("message %s job %s via %s -> %s (attempt %s, to %s)", message.id, job.id, channel.provider,
             message.status, attempt_no, mask(customer.phone))
    db.commit()
    return message


def _fail(db: Session, message: NotificationMessage, t: datetime, code: str, error: str,
          commit: bool = True) -> NotificationMessage:
    message.status, message.failed_at, message.next_retry_at = "failed", t, None
    message.error_code, message.error = code or "failed", (error or "Delivery failed")[:300]
    message.updated_at = t
    log.warning("message %s failed: %s", message.id, message.error_code)
    if commit:
        db.commit()
    return message


def _record_attempt(db: Session, message: NotificationMessage, attempt_no: int, provider: str, t: datetime,
                    result: SendResult) -> None:
    outcome = {"accepted": "accepted", "retryable_error": "retryable_error"}.get(result.outcome, "permanent_error")
    if result.outcome == "unknown":
        outcome = "unknown"
    db.add(DeliveryAttempt(message_id=message.id, attempt_no=attempt_no, provider=provider, requested_at=t,
                           outcome=outcome, http_status=result.http_status, error_code=result.error_code,
                           error_message=result.error_message[:300], provider_message_id=result.provider_message_id))


def _finalise_job(db: Session, job: NotificationJob, t: datetime) -> None:
    recount(db, job)
    job.processed_at = job.processed_at or t
    msgs = job.messages
    job.simulated = all(m.simulated for m in msgs) if msgs else True
    if not msgs:
        job.status = "sent"
        job.note = job.note or "No eligible recipients (consent, preference or account status)"
    elif all(m.status == "failed" for m in msgs):
        job.status = "failed"
    else:
        job.status = "sent"
    if job.scheduled_outage is not None and job.sent_count:
        # Later reschedules/cancellations notify customers only if someone was actually reached.
        job.scheduled_outage.customers_notified = True


def recount(db: Session, job: NotificationJob) -> None:
    db.flush()
    msgs = db.scalars(select(NotificationMessage).where(NotificationMessage.job_id == job.id)).all()
    job.recipients_count = len(msgs)
    job.sent_count = sum(1 for m in msgs if m.status in ACCEPTED)
    job.failed_count = sum(1 for m in msgs if m.status == "failed")


def retry_failed(db: Session, job: NotificationJob) -> NotificationJob:
    """Operator-initiated retry of failed messages (including unknown outcomes, which are never auto-retried)."""
    if job.status not in ("sent", "failed") or not job.failed_count:
        raise conflict("this notification has no failed messages to retry")
    t = clock_now()
    router = get_router()
    router.failure_rate = settings_store.get_section(db, "notifications").simulated_failure_rate
    failed = db.scalars(select(NotificationMessage).where(NotificationMessage.job_id == job.id,
                                                          NotificationMessage.status == "failed",
                                                          NotificationMessage.provider_message_id.is_(None))).all()
    for message in failed:
        route = router.route(message.customer)
        if route.channel is None:
            continue  # no longer eligible (e.g. consent withdrawn): leave it failed
        message.status, message.provider, message.channel = "queued", route.channel.provider, route.channel.channel
        message.simulated = route.channel.simulated
        message.error_code, message.error, message.failed_at = "", "", None
    db.commit()
    for message in failed:
        if message.status == "queued":
            deliver(db, message)
    db.refresh(job)
    _finalise_job(db, job, t)
    activity.log(db, "notification_retry", f"Retried failed messages for notification #{job.id}: "
                 f"{job.sent_count} sent, {job.failed_count} still failing",
                 severity="warning" if job.failed_count else "success", entity_type="notification", entity_id=job.id)
    db.commit()
    return job


def process_due(db: Session, at: datetime | None = None) -> int:
    """Scheduler entry point: due jobs, due message retries, interrupted sends, mock delivery receipts."""
    at = at or clock_now()
    sent = 0
    # A job left in 'processing' (crash mid-send) is resumed; per-message claims prevent duplicates.
    for job_id in db.scalars(select(NotificationJob.id).where(NotificationJob.status == "processing")).all():
        send_job(db, db.get(NotificationJob, job_id), claimed=True)
        sent += 1
    due = db.scalars(select(NotificationJob.id).where(NotificationJob.status == "scheduled",
                                                      NotificationJob.send_at <= at)
                     .order_by(NotificationJob.send_at)).all()
    for job_id in due:
        if _claim_job(db, job_id, ("scheduled",)):
            send_job(db, db.get(NotificationJob, job_id), claimed=True)
            sent += 1
    _process_retries(db, at)
    _expire_stuck_sends(db, at)
    _simulate_mock_receipts(db, at)
    return sent


def _process_retries(db: Session, at: datetime) -> None:
    router = get_router()
    router.failure_rate = settings_store.get_section(db, "notifications").simulated_failure_rate
    due = db.scalars(select(NotificationMessage.id).where(NotificationMessage.status == "retry_scheduled",
                                                          NotificationMessage.next_retry_at <= at)).all()
    touched: set[int] = set()
    for message_id in due:
        message = deliver(db, db.get(NotificationMessage, message_id))
        touched.add(message.job_id)
    for job_id in touched:
        job = db.get(NotificationJob, job_id)
        _finalise_job(db, job, at)
    db.commit()


def _expire_stuck_sends(db: Session, at: datetime) -> None:
    stuck = db.scalars(select(NotificationMessage).where(NotificationMessage.status == "sending",
                                                         NotificationMessage.updated_at < at - STUCK_SENDING)).all()
    for message in stuck:
        _fail(db, message, at, "outcome_unknown",
              "Send was interrupted; the message may have been delivered. Not retried automatically.", commit=False)
        recount(db, message.job)
    db.commit()


def _simulate_mock_receipts(db: Session, at: datetime) -> None:
    """In mock mode there are no provider webhooks, so simulated messages progress sent -> delivered -> read."""
    candidates = db.scalars(select(NotificationMessage).where(
        NotificationMessage.simulated.is_(True),
        or_(NotificationMessage.status == "sent", NotificationMessage.status == "delivered"),
        NotificationMessage.updated_at < at - timedelta(seconds=8))).all()
    for message in candidates:
        if message.status == "sent":
            message.status, message.delivered_at = "delivered", at
        elif int(hashlib.sha1(str(message.id).encode()).hexdigest(), 16) % 3 == 0:
            message.status, message.read_at = "read", at
        else:
            continue
        message.updated_at = at
    db.commit()


def apply_status_update(db: Session, message: NotificationMessage, status: str, ts: datetime,
                        error_code: str = "", error: str = "") -> bool:
    """Apply a provider delivery status. Statuses only move forward (sent < delivered < read)."""
    if status == "failed":
        if message.status in ("delivered", "read"):
            return False
        _fail(db, message, ts, error_code or "provider_failed", error or "Delivery failed (reported by provider)",
              commit=False)
        recount(db, message.job)
        return True
    if status not in STATUS_RANK or STATUS_RANK[status] <= STATUS_RANK.get(message.status, -1):
        return False
    message.status = status
    if status == "sent":
        message.sent_at = message.sent_at or ts
    elif status == "delivered":
        message.delivered_at = ts
    elif status == "read":
        message.read_at = ts
        message.delivered_at = message.delivered_at or ts
    message.updated_at = clock_now()
    return True


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
    router = get_router()
    channels: dict[str, int] = {}
    for c in aud["eligible"]:
        route = router.route(c)
        key = "blocked" if route.blocked_reason else f"{route.channel.channel}:{'simulated' if route.channel.simulated else 'live'}"
        channels[key] = channels.get(key, 0) + 1
    return {
        "body": rendered,
        "missing_placeholders": missing_placeholders(rendered),
        "recipients": {
            "eligible": len(aud["eligible"]),
            "total_in_areas": len(aud["customers"]),
            "excluded": aud["excluded"],
            "channels": channels,
        },
        "simulated": not router.config.whatsapp_live,
    }


def describe_config(config: Config) -> str:
    return "live" if config.whatsapp_live else "mock"
