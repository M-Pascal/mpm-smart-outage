"""Aggregates for the analytics page and monitoring charts. All data is simulated demo data."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from statistics import mean
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..clock import iso
from ..clock import now as clock_now
from ..models import AreaReading, Incident, MeterReading, NotificationJob, NotificationMessage, ScheduledOutage, ServiceArea

RANGES = {  # range -> (window, bucket)
    "1h": (timedelta(hours=1), timedelta(minutes=1)),
    "6h": (timedelta(hours=6), timedelta(minutes=5)),
    "24h": (timedelta(hours=24), timedelta(minutes=15)),
    "7d": (timedelta(days=7), timedelta(hours=1)),
}


def _bucket(ts: datetime, start: datetime, size: timedelta) -> datetime:
    n = int((ts - start).total_seconds() // size.total_seconds())
    return start + n * size


def series(db: Session, range_: str, area_id: int | None = None) -> list[dict[str, Any]]:
    window, size = RANGES[range_]
    t = clock_now()
    start = t - window
    q = select(AreaReading.service_area_id, AreaReading.ts, AreaReading.avg_voltage, AreaReading.total_power_kw,
               AreaReading.meters_reporting).where(AreaReading.ts >= start, AreaReading.ts <= t)
    if area_id:
        q = q.where(AreaReading.service_area_id == area_id)
    # bucket -> area -> [(voltage, reporting, power)]
    buckets: dict[datetime, dict[int, list[tuple]]] = defaultdict(lambda: defaultdict(list))
    for aid, ts, v, p, n in db.execute(q):
        buckets[_bucket(ts, start, size)][aid].append((v, n, p))
    out = []
    for b in sorted(buckets):
        volt_num = volt_den = 0.0
        power = 0.0
        for rows in buckets[b].values():
            power += mean(p for _, _, p in rows)
            for v, n, _ in rows:
                if v is not None and n:
                    volt_num += v * n
                    volt_den += n
        out.append({"ts": iso(b), "voltage": round(volt_num / volt_den, 1) if volt_den else None,
                    "power_kw": round(power, 2)})
    return out


def meter_series(db: Session, meter_id: int, range_: str) -> list[dict[str, Any]]:
    window, size = RANGES[range_]
    t = clock_now()
    start = t - window
    buckets: dict[datetime, list[tuple]] = defaultdict(list)
    for ts, v, c, p in db.execute(select(MeterReading.ts, MeterReading.voltage, MeterReading.current, MeterReading.power_kw)
                                  .where(MeterReading.meter_id == meter_id, MeterReading.ts >= start, MeterReading.ts <= t)):
        buckets[_bucket(ts, start, size)].append((v, c, p))
    return [{"ts": iso(b), "voltage": round(mean(r[0] for r in rows), 1), "current": round(mean(r[1] for r in rows), 2),
             "power_kw": round(mean(r[2] for r in rows), 3)} for b, rows in sorted(buckets.items())]


def _avg(values: list[float]) -> float | None:
    return round(mean(values), 1) if values else None


def analytics(db: Session, days: int = 90) -> dict[str, Any]:
    t = clock_now()
    since = t - timedelta(days=days)
    incidents = db.scalars(select(Incident).where(Incident.detected_at >= since)).all()
    real_incidents = [i for i in incidents if i.verification_status != "rejected"]
    planned = db.scalars(select(ScheduledOutage).where(ScheduledOutage.start_at >= since)).all()
    jobs = db.scalars(select(NotificationJob).where(NotificationJob.created_at >= since)).all()
    msgs = db.scalars(select(NotificationMessage).where(NotificationMessage.created_at >= since)).all()
    areas = db.scalars(select(ServiceArea)).all()

    incident_minutes = [(i.power_restored_at - (i.first_evidence_at or i.detected_at)).total_seconds() / 60
                        for i in real_incidents if i.power_restored_at]
    planned_done = [o for o in planned if o.status in ("completed", "in_progress")]
    planned_minutes = [(o.end_at - o.start_at).total_seconds() / 60 for o in planned_done]
    detection = [(i.detected_at - i.first_evidence_at).total_seconds() for i in real_incidents if i.first_evidence_at]
    confirmation = [(i.confirmed_at - i.detected_at).total_seconds() for i in real_incidents if i.confirmed_at]

    jobs_by_incident: dict[int, list[NotificationJob]] = defaultdict(list)
    jobs_by_outage: dict[int, list[NotificationJob]] = defaultdict(list)
    for j in jobs:
        if j.incident_id:
            jobs_by_incident[j.incident_id].append(j)
        if j.scheduled_outage_id:
            jobs_by_outage[j.scheduled_outage_id].append(j)
    prep = []
    for i in real_incidents:
        alerts = [j for j in jobs_by_incident.get(i.id, []) if j.kind == "outage_alert"]
        if alerts:
            prep.append((min(j.created_at for j in alerts) - i.detected_at).total_seconds())
    lead = []
    for o in planned:
        notices = [j for j in jobs_by_outage.get(o.id, []) if j.kind == "notice" and j.status == "sent"]
        if notices and o.status != "cancelled":
            lead.append((o.start_at - min(j.processed_at or j.send_at for j in notices)).total_seconds() / 3600)

    sent = sum(1 for m in msgs if m.status in ("sent", "delivered", "read"))
    delivered = sum(1 for m in msgs if m.status in ("delivered", "read"))
    read = sum(1 for m in msgs if m.status == "read")
    failed = sum(1 for m in msgs if m.status == "failed")

    area_stats = []
    for a in areas:
        a_inc = [i for i in real_incidents if i.service_area_id == a.id]
        a_plan = [o for o in planned if o.status != "cancelled" and a in o.service_areas]
        cust_hours = sum(i.estimated_customers * (((i.power_restored_at or t) - (i.first_evidence_at or i.detected_at))
                                                  .total_seconds() / 3600) for i in a_inc)
        cust_hours += sum(len(a.customers) * (o.end_at - o.start_at).total_seconds() / 3600
                          for o in a_plan if o.status in ("completed", "in_progress"))
        area_stats.append({"service_area_id": a.id, "name": a.name, "code": a.code, "unexpected": len(a_inc),
                           "planned": len(a_plan), "customer_hours_lost": round(cust_hours, 1)})
    area_stats.sort(key=lambda s: (s["unexpected"] + s["planned"], s["customer_hours_lost"]), reverse=True)

    weeks = []
    for w in range(11, -1, -1):
        w_start = t - timedelta(weeks=w + 1)
        w_end = t - timedelta(weeks=w)
        weeks.append({
            "week_start": iso(w_start),
            "planned": sum(1 for o in planned if o.status != "cancelled" and o.status != "draft" and w_start <= o.start_at < w_end),
            "unexpected": sum(1 for i in real_incidents if w_start <= i.detected_at < w_end),
        })

    by_kind: dict[str, dict[str, int]] = defaultdict(lambda: {"sent": 0, "failed": 0})
    job_kind = {j.id: j.kind for j in jobs}
    for m in msgs:
        kind = job_kind.get(m.job_id, "other")
        if m.status in ("sent", "delivered", "read"):
            by_kind[kind]["sent"] += 1
        elif m.status == "failed":
            by_kind[kind]["failed"] += 1

    severity = defaultdict(int)
    for i in real_incidents:
        severity[i.severity] += 1

    return {
        "simulated": True,
        "period_days": days,
        "kpis": {
            "planned_interruptions": sum(1 for o in planned if o.status not in ("draft", "cancelled")),
            "cancelled_interruptions": sum(1 for o in planned if o.status == "cancelled"),
            "unexpected_outages": len(real_incidents),
            "confirmed_outages": sum(1 for i in real_incidents if i.verification_status == "confirmed"),
            "avg_unexpected_duration_min": _avg(incident_minutes),
            "avg_planned_duration_min": _avg(planned_minutes),
            "avg_detection_seconds": _avg(detection),
            "avg_confirmation_seconds": _avg(confirmation),
            "avg_notification_prep_seconds": _avg(prep),
            "avg_advance_notice_hours": _avg(lead),
            "messages_sent": sent,
            "messages_failed": failed,
            "messages_delivered": delivered,
            "messages_read": read,
            "delivery_rate": round(delivered / sent, 4) if sent else 0,
            "simulated_share": round(sum(1 for m in msgs if m.simulated) / len(msgs), 4) if msgs else 1,
            "failure_rate": round(failed / (sent + failed), 4) if sent + failed else 0,
        },
        "weekly": weeks,
        "areas": area_stats,
        "messages_by_kind": [{"kind": k, **v} for k, v in sorted(by_kind.items())],
        "severity": [{"severity": s, "count": severity.get(s, 0)} for s in ("low", "medium", "high", "critical")],
        "durations": [{"code": f"INC-{i.id:04d}", "area": i.service_area.name,
                       "minutes": round(((i.power_restored_at or t) - (i.first_evidence_at or i.detected_at)).total_seconds() / 60, 1),
                       "detected_at": iso(i.detected_at)}
                      for i in sorted(real_incidents, key=lambda x: x.detected_at)],
    }
