"""Model -> JSON dictionaries for API responses."""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from .clock import iso
from .models import (
    ActivityLog, Customer, Incident, Meter, MiniGrid, NotificationJob, NotificationMessage, NotificationTemplate,
    ScheduledOutage, ServiceArea,
)
from .services import incidents as incident_svc
from .services import scheduled_outages as outage_svc
from .channels.router import get_router
from .phone import is_valid
from .services.notifications import KIND_LABELS, REASON_LABELS


def mask_phone(phone: str) -> str:
    return phone if len(phone) < 8 else f"{phone[:7]}•••{phone[-3:]}"


def area(a: ServiceArea, stats: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"id": a.id, "code": a.code, "name": a.name, "description": a.description, "mini_grid_id": a.mini_grid_id,
            "mini_grid_name": a.mini_grid.name, "sim_scenario": a.sim_scenario, "source": a.source,
            "mpm_city_id": a.mpm_city_id, **(stats or {})}


def mini_grid(g: MiniGrid) -> dict[str, Any]:
    return {"id": g.id, "name": g.name, "district": g.district, "capacity_kw": g.capacity_kw, "source": g.source,
            "mpm_id": g.mpm_id,
            "service_areas": [{"id": a.id, "code": a.code, "name": a.name} for a in g.service_areas]}


def customer(c: Customer, *, full_phone: bool = True) -> dict[str, Any]:
    route = get_router().route(c)
    reason = route.excluded_reason
    return {
        "id": c.id, "code": f"CUS-{c.id:04d}", "name": c.name,
        "phone": c.phone if full_phone else mask_phone(c.phone),
        "service_area_id": c.service_area_id, "service_area_name": c.service_area.name,
        "customer_type": c.customer_type, "notification_preference": c.notification_preference,
        "whatsapp_opt_in": c.whatsapp_opt_in, "account_status": c.account_status, "notes": c.notes,
        "meter_id": c.meter.id if c.meter else None, "meter_serial": c.meter.serial if c.meter else None,
        "notifications_eligible": reason is None, "ineligible_reason": reason,
        "notification_channel": route.channel.channel if route.channel else None,
        "delivery_blocked_reason": route.blocked_reason, "phone_valid": is_valid(c.phone),
        "consent_source": c.consent_source, "consent_updated_at": iso(c.consent_updated_at),
        "source": c.source, "mpm_person_id": c.mpm_person_id, "last_synced_at": iso(c.last_synced_at),
        "created_at": iso(c.created_at), "updated_at": iso(c.updated_at),
    }


def meter(m: Meter) -> dict[str, Any]:
    return {
        "id": m.id, "serial": m.serial, "service_area_id": m.service_area_id, "service_area_name": m.service_area.name,
        "customer_id": m.customer_id, "customer_name": m.customer.name if m.customer else None,
        "status": m.status, "voltage": m.last_voltage, "current": m.last_current, "power_kw": m.last_power_kw,
        "last_reading_at": iso(m.last_reading_at), "status_since": iso(m.status_since),
        "pending_status": m.pending_status, "pending_count": m.pending_count,
        "sim_scenario": m.sim_scenario or m.service_area.sim_scenario, "source": m.source,
    }


def job(j: NotificationJob, db: Session | None = None) -> dict[str, Any]:
    linked = None
    if j.scheduled_outage is not None:
        linked = {"type": "scheduled_outage", "id": j.scheduled_outage_id, "code": outage_svc.code(j.scheduled_outage),
                  "title": j.scheduled_outage.title}
    elif j.incident is not None:
        linked = {"type": "incident", "id": j.incident_id, "code": incident_svc.code(j.incident),
                  "title": f"Unexpected outage – {j.incident.service_area.name}"}
    statuses = [m.status for m in j.messages]
    return {
        "id": j.id, "code": f"NTF-{j.id:04d}", "kind": j.kind, "kind_label": KIND_LABELS.get(j.kind, j.kind),
        "template_key": j.template_key, "area_ids": j.area_ids, "context": j.context,
        "send_at": iso(j.send_at), "offset_minutes": j.offset_minutes, "status": j.status,
        "recipients_count": j.recipients_count, "sent_count": j.sent_count, "failed_count": j.failed_count,
        "delivered_count": sum(1 for s in statuses if s in ("delivered", "read")),
        "read_count": sum(1 for s in statuses if s == "read"),
        "pending_count": sum(1 for s in statuses if s in ("queued", "sending", "retry_scheduled")),
        "channels": sorted({m.channel for m in j.messages}),
        "note": j.note, "created_by": j.created_by, "created_at": iso(j.created_at), "processed_at": iso(j.processed_at),
        "linked": linked, "simulated": j.simulated,
    }


def message(m: NotificationMessage) -> dict[str, Any]:
    return {"id": m.id, "job_id": m.job_id, "customer_id": m.customer_id, "customer_name": m.customer.name,
            "service_area_name": m.customer.service_area.name, "phone": mask_phone(m.phone), "body": m.body,
            "status": m.status, "channel": m.channel, "provider": m.provider, "simulated": m.simulated,
            "provider_message_id": m.provider_message_id, "attempts": m.attempts, "error_code": m.error_code,
            "error": m.error, "next_retry_at": iso(m.next_retry_at), "sent_at": iso(m.sent_at),
            "delivered_at": iso(m.delivered_at), "read_at": iso(m.read_at), "failed_at": iso(m.failed_at),
            "created_at": iso(m.created_at), "updated_at": iso(m.updated_at)}


def delivery_attempt(a) -> dict[str, Any]:  # noqa: ANN001
    return {"attempt_no": a.attempt_no, "provider": a.provider, "requested_at": iso(a.requested_at),
            "outcome": a.outcome, "http_status": a.http_status, "error_code": a.error_code,
            "error_message": a.error_message, "provider_message_id": a.provider_message_id}


def template(t: NotificationTemplate) -> dict[str, Any]:
    return {"id": t.id, "key": t.key, "name": t.name, "category": t.category, "description": t.description,
            "body": t.body, "updated_at": iso(t.updated_at)}


def scheduled_outage(o: ScheduledOutage, db: Session, *, jobs: bool = False) -> dict[str, Any]:
    from .services.notifications import audience

    area_ids = [a.id for a in o.service_areas]
    aud = audience(db, area_ids)
    data = {
        "id": o.id, "code": outage_svc.code(o), "title": o.title, "reason": o.reason,
        "reason_label": REASON_LABELS.get(o.reason, o.reason), "reason_detail": o.reason_detail,
        "mini_grid_id": o.mini_grid_id, "mini_grid_name": o.mini_grid.name,
        "service_areas": [{"id": a.id, "code": a.code, "name": a.name} for a in o.service_areas],
        "start_at": iso(o.start_at), "end_at": iso(o.end_at), "description": o.description, "priority": o.priority,
        "status": o.status, "reminder_offsets": o.reminder_offsets, "send_notice_on_publish": o.send_notice_on_publish,
        "customers_notified": o.customers_notified, "published_at": iso(o.published_at),
        "cancelled_at": iso(o.cancelled_at), "cancel_reason": o.cancel_reason, "reschedule_count": o.reschedule_count,
        "affected_customers": len(aud["customers"]), "eligible_recipients": len(aud["eligible"]),
        "created_at": iso(o.created_at), "updated_at": iso(o.updated_at),
    }
    from sqlalchemy import select

    all_jobs = db.scalars(select(NotificationJob).where(NotificationJob.scheduled_outage_id == o.id)
                          .order_by(NotificationJob.send_at)).all()
    data["notifications_pending"] = sum(1 for j in all_jobs if j.status in ("draft", "scheduled"))
    data["notifications_sent"] = sum(1 for j in all_jobs if j.status == "sent")
    nxt = next((j for j in all_jobs if j.status == "scheduled"), None)
    data["next_notification_at"] = iso(nxt.send_at) if nxt else None
    if jobs:
        data["notifications"] = [job(j) for j in all_jobs]
    return data


def incident(i: Incident, db: Session, *, detail: bool = False) -> dict[str, Any]:
    data = {
        "id": i.id, "code": incident_svc.code(i), "service_area_id": i.service_area_id,
        "service_area_name": i.service_area.name, "mini_grid_name": i.service_area.mini_grid.name,
        "scope": i.scope, "evidence_type": i.evidence_type, "severity": i.severity, "verification_status": i.verification_status,
        "resolution_status": i.resolution_status, "confirmation_method": i.confirmation_method,
        "first_evidence_at": iso(i.first_evidence_at), "detected_at": iso(i.detected_at),
        "confirmed_at": iso(i.confirmed_at), "acknowledged_at": iso(i.acknowledged_at),
        "acknowledged_by": i.acknowledged_by, "power_restored_at": iso(i.power_restored_at),
        "resolved_at": iso(i.resolved_at), "affected_meters": len(i.affected_meter_ids),
        "peak_affected_meters": i.peak_affected_meters, "area_meter_count": len(i.service_area.meters),
        "estimated_customers": i.estimated_customers, "resolution_note": i.resolution_note,
        "restoration_suggested": incident_svc.restoration_suggested(db, i),
    }
    if detail:
        from sqlalchemy import select

        data["events"] = [{"id": e.id, "ts": iso(e.ts), "type": e.type, "message": e.message, "actor": e.actor}
                          for e in i.events]
        data["notifications"] = [job(j) for j in db.scalars(
            select(NotificationJob).where(NotificationJob.incident_id == i.id).order_by(NotificationJob.send_at))]
        data["affected_meter_list"] = [meter(m) for m in i.service_area.meters if m.id in i.affected_meter_ids]
    return data


def activity_entry(a: ActivityLog) -> dict[str, Any]:
    return {"id": a.id, "ts": iso(a.ts), "type": a.type, "severity": a.severity, "message": a.message,
            "entity_type": a.entity_type, "entity_id": a.entity_id, "operator_alert": a.operator_alert, "read": a.read}
