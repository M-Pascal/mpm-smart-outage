"""Demo seed data. Every person, phone number and location here is fictional."""
from __future__ import annotations

import random
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .clock import now as clock_now
from .models import (
    ActivityLog, AreaReading, Customer, Incident, IncidentEvent, Meter, MeterReading, MiniGrid,
    NotificationJob, NotificationMessage, NotificationTemplate, ScheduledOutage, ServiceArea,
)
from .services import monitoring
from .channels.base import OutboundMessage
from .channels.mock import MockChannel
from .services.notifications import eligibility
from .services.templates import DEFAULT_TEMPLATES, render
from .services.timefmt import fmt_date, fmt_time

TZ = "Africa/Kigali"

GRIDS = [
    ("Kivu Ridge Mini-Grid", "Lakeshore District", 120.0, [
        ("A", "Sector A – Market Centre", "Shops, market stalls and the market clinic"),
        ("B", "Sector B – Hillside", "Residential homes on the eastern hillside"),
        ("C", "Sector C – School Road", "Primary school, homes and small businesses"),
    ]),
    ("Akagera Valley Mini-Grid", "Valley District", 85.0, [
        ("D", "Sector D – Riverside", "Riverside homes and irrigation pumps"),
        ("E", "Sector E – Farm Cooperative", "Maize mill and cooperative buildings"),
    ]),
]

# (area, name, type, preference, opt_in, status, has_meter)
CUSTOMERS = [
    ("A", "Market Clinic", "essential_service", "whatsapp", True, "active", True),
    ("A", "Umurava Grocery", "commercial", "whatsapp", True, "active", True),
    ("A", "Aline Mukeshimana", "residential", "whatsapp", True, "active", True),
    ("A", "Didier Nkurunziza", "residential", "whatsapp", True, "active", True),
    ("A", "Ineza Tailoring", "commercial", "sms", False, "active", True),
    ("A", "Josiane Uwera", "residential", "whatsapp", True, "active", True),
    ("A", "Samuel Rwigema", "residential", "whatsapp", True, "active", False),
    ("A", "Kevin Habimana", "residential", "whatsapp", False, "active", True),
    ("B", "Claudine Mutesi", "residential", "whatsapp", True, "active", True),
    ("B", "Emmanuel Ndayisaba", "residential", "whatsapp", True, "active", True),
    ("B", "Grace Uwamahoro", "residential", "whatsapp", True, "active", True),
    ("B", "Patrick Munyaneza", "residential", "whatsapp", True, "suspended", True),
    ("B", "Hillside Barber", "commercial", "whatsapp", True, "active", True),
    ("B", "Vestine Nyirahabimana", "residential", "none", False, "active", False),
    ("B", "Olivier Kayitare", "residential", "whatsapp", True, "active", True),
    ("C", "Bright Future Primary School", "public_institution", "whatsapp", True, "active", True),
    ("C", "School Road Pharmacy", "essential_service", "whatsapp", True, "active", True),
    ("C", "Jeanne Ingabire", "residential", "whatsapp", True, "active", True),
    ("C", "Eric Mugisha", "residential", "whatsapp", True, "active", True),
    ("C", "Sandrine Umutoni", "residential", "sms", True, "active", True),
    ("C", "Yves Niyonsaba", "residential", "whatsapp", True, "active", False),
    ("C", "Chantal Mukamana", "residential", "whatsapp", True, "inactive", True),
    ("D", "Riverside Irrigation Pump 1", "productive_use", "whatsapp", True, "active", True),
    ("D", "Theogene Bizimana", "residential", "whatsapp", True, "active", True),
    ("D", "Alice Uwimana", "residential", "whatsapp", True, "active", True),
    ("D", "Jean Paul Hakizimana", "residential", "whatsapp", False, "active", True),
    ("D", "Riverside Kiosk", "commercial", "whatsapp", True, "active", True),
    ("D", "Divine Iradukunda", "residential", "whatsapp", True, "active", False),
    ("D", "Fabrice Nshimiyimana", "residential", "whatsapp", True, "active", True),
    ("E", "Valley Maize Mill", "productive_use", "whatsapp", True, "active", True),
    ("E", "Cooperative Office", "public_institution", "whatsapp", True, "active", True),
    ("E", "Esperance Mukandayisenga", "residential", "whatsapp", True, "active", True),
    ("E", "Innocent Habiyaremye", "residential", "whatsapp", True, "active", True),
    ("E", "Valley Health Post", "essential_service", "whatsapp", True, "active", True),
    ("E", "Marie Claire Uwase", "residential", "sms", False, "active", False),
    ("E", "Jean de Dieu Mugabo", "residential", "whatsapp", True, "active", True),
]

PLANNED_REASONS = ["planned_maintenance", "equipment_replacement", "network_upgrade", "load_shedding",
                   "safety_inspection"]


def local_dt(day: datetime, hh: int, mm: int = 0) -> datetime:
    """UTC-naive datetime for a local wall-clock time on the local date of `day`."""
    tz = ZoneInfo(TZ)
    local_date = day.replace(tzinfo=timezone.utc).astimezone(tz).date()
    return datetime.combine(local_date, time(hh, mm), tzinfo=tz).astimezone(timezone.utc).replace(tzinfo=None)


def is_seeded(db: Session) -> bool:
    return db.scalar(select(func.count()).select_from(MiniGrid)) > 0


def seed(db: Session) -> None:
    rng = random.Random(7)
    t0 = clock_now().replace(microsecond=0)

    for tpl in DEFAULT_TEMPLATES:
        db.add(NotificationTemplate(**tpl))

    areas: dict[str, ServiceArea] = {}
    grids: dict[str, MiniGrid] = {}
    for gname, district, cap, area_defs in GRIDS:
        grid = MiniGrid(name=gname, district=district, capacity_kw=cap)
        db.add(grid)
        grids[gname] = grid
        for code, name, desc in area_defs:
            area = ServiceArea(code=code, name=name, description=desc, mini_grid=grid, created_at=t0 - timedelta(days=400))
            db.add(area)
            areas[code] = area
    db.flush()

    meters: list[Meter] = []
    customers: list[Customer] = []
    for i, (acode, name, ctype, pref, opt_in, status, has_meter) in enumerate(CUSTOMERS, start=1):
        c = Customer(name=name, phone=f"+250700100{i:03d}", service_area=areas[acode], customer_type=ctype,
                     notification_preference=pref, whatsapp_opt_in=opt_in, account_status=status,
                     created_at=t0 - timedelta(days=300 - i * 3))
        db.add(c)
        customers.append(c)
        if has_meter:
            m = Meter(serial=f"PC-{acode}{i:03d}", service_area=areas[acode], customer=c, status="normal",
                      status_since=t0 - timedelta(days=2), created_at=t0 - timedelta(days=300),
                      last_voltage=230.0, last_current=0.0, last_power_kw=0.0, last_reading_at=t0)
            db.add(m)
            meters.append(m)
    db.flush()

    history_incidents = _seed_incidents(db, rng, t0, areas)
    _seed_planned(db, rng, t0, areas, grids)
    _seed_readings(db, rng, t0, meters, areas, history_incidents)
    db.add(ActivityLog(ts=t0 - timedelta(minutes=1), type="system", severity="info",
                       message="PowerChat demo data loaded (simulated meters, fictional customers)"))
    db.commit()


# ----------------------------------------------------------------- helpers
def _history_job(db: Session, rng: random.Random, *, kind: str, template_key: str, area_ids: list[int],
                 send_at: datetime, ctx: dict, outage: ScheduledOutage | None = None, incident: Incident | None = None,
                 offset: int | None = None) -> NotificationJob:
    job = NotificationJob(kind=kind, template_key=template_key, area_ids=area_ids, send_at=send_at,
                          status="sent", simulated=True, scheduled_outage=outage, incident=incident, offset_minutes=offset,
                          created_at=send_at - timedelta(seconds=1), processed_at=send_at,
                          created_by="system", context={})
    db.add(job)
    db.flush()
    body = next(t["body"] for t in DEFAULT_TEMPLATES if t["key"] == template_key)
    recips = db.scalars(select(Customer).where(Customer.service_area_id.in_(area_ids))).all()
    sent = failed = 0
    for c in recips:
        if eligibility(c) is not None:
            continue
        channel = "sms" if c.notification_preference == "sms" else "whatsapp"
        text = render(body, {**ctx, "area": c.service_area.name})
        result = MockChannel(channel, 0.08).send(OutboundMessage(
            to=c.phone, template=template_key, language="en", parameters=[], body=text, reference=f"{job.id}-{c.id}"))
        success = result.outcome == "accepted"
        # Historic simulated messages: most were delivered, about a third were also read.
        status = "failed" if not success else ("read" if (job.id + c.id) % 3 == 0 else "delivered")
        db.add(NotificationMessage(
            job_id=job.id, customer_id=c.id, phone=c.phone, body=text, status=status, channel=channel, provider="mock",
            simulated=True, provider_message_id=result.provider_message_id, attempts=1,
            error_code=result.error_code, error=result.error_message,
            sent_at=send_at if success else None, delivered_at=send_at + timedelta(seconds=40) if success else None,
            read_at=send_at + timedelta(minutes=12) if status == "read" else None,
            failed_at=None if success else send_at, created_at=send_at, updated_at=send_at))
        sent += success
        failed += not success
    job.recipients_count, job.sent_count, job.failed_count = sent + failed, sent, failed
    if failed and not sent:
        job.status = "failed"
    return job


def _seed_incidents(db: Session, rng: random.Random, t0: datetime, areas: dict[str, ServiceArea]) -> list[tuple]:
    history = []
    plan = [(52, "D", 95, "high"), (44, "B", 40, "medium"), (37, "E", 150, "critical"), (29, "A", 25, "low"),
            (21, "C", 70, "high"), (15, "D", 55, "high"), (11, "B", 15, "low"), (6, "E", 120, "high"),
            (4, "A", 45, "critical"), (2, "C", 30, "medium")]
    for days_ago, acode, minutes, severity in plan:
        area = areas[acode]
        start = local_dt(t0 - timedelta(days=days_ago), rng.randint(7, 20), rng.choice([5, 20, 35, 50]))
        detected = start + timedelta(seconds=rng.randint(8, 25))
        confirmed = detected + timedelta(seconds=rng.randint(6, 40)) if severity != "low" else None
        restored = start + timedelta(minutes=minutes)
        n_meters = len([m for m in area.meters])
        affected = 1 if severity == "low" else (max(2, n_meters // 2) if severity == "medium" else n_meters)
        inc = Incident(service_area=area, scope="meter" if severity == "low" else "area", severity=severity,
                       verification_status="confirmed" if confirmed else "potential", resolution_status="resolved",
                       confirmation_method="auto" if confirmed else None, first_evidence_at=start,
                       detected_at=detected, confirmed_at=confirmed,
                       acknowledged_at=detected + timedelta(minutes=rng.randint(1, 6)), acknowledged_by="Admin Operator",
                       power_restored_at=restored, resolved_at=restored + timedelta(minutes=rng.randint(0, 10)),
                       peak_affected_meters=affected,
                       estimated_customers=max(affected, round(len(area.customers) * affected / max(1, n_meters))),
                       resolution_note="Power restored; incident closed." if confirmed else
                       "Single meter fault at customer premises.", is_seed=True, created_at=detected)
        db.add(inc)
        db.flush()
        events = [(detected, "detected", f"Potential outage detected: {affected} of {n_meters} meters in {area.name} report no supply")]
        if confirmed:
            events.append((confirmed, "confirmed", "Outage confirmed automatically (sufficient monitoring evidence)"))
            ctx = {"organization": "PowerChat Energy"}
            job = _history_job(db, rng, kind="outage_alert", template_key="unexpected_outage", area_ids=[area.id],
                               send_at=confirmed + timedelta(seconds=2), ctx=ctx, incident=inc)
            events.append((job.send_at, "notification", f"Customer outage alert sent to {job.sent_count} customers"))
            if minutes >= 90:
                job2 = _history_job(db, rng, kind="restoration", template_key="power_restored", area_ids=[area.id],
                                    send_at=restored + timedelta(minutes=5), ctx=ctx, incident=inc)
                events.append((job2.send_at, "notification", f"Restoration announcement sent to {job2.sent_count} customers"))
        events.append((inc.acknowledged_at, "acknowledged", "Acknowledged by Admin Operator"))
        events.append((restored, "power_restored", "Power restored: all meters report normal voltage"))
        events.append((inc.resolved_at, "resolved", inc.resolution_note))
        code = f"INC-{inc.id:04d}"
        db.add(ActivityLog(ts=detected, type="outage_detected", severity="warning", entity_type="incident", entity_id=inc.id,
                           read=True, operator_alert=True, message=f"{code}: potential outage in {area.name}"))
        if confirmed:
            db.add(ActivityLog(ts=confirmed, type="outage_confirmed", severity="critical", entity_type="incident",
                               entity_id=inc.id, read=True, message=f"{code} confirmed automatically in {area.name}"))
        db.add(ActivityLog(ts=inc.resolved_at, type="outage_resolved", severity="success", entity_type="incident",
                           entity_id=inc.id, message=f"{code} in {area.name} resolved"))
        for ts, typ, msg in sorted(events, key=lambda e: e[0]):
            db.add(IncidentEvent(incident_id=inc.id, ts=ts, type=typ, message=msg,
                                 actor="Admin Operator" if typ == "acknowledged" else "system"))
        history.append((area.id, start, restored, affected == n_meters))
    return history


def _outage(db: Session, *, title: str, reason: str, grid: MiniGrid, area_list: list[ServiceArea], start: datetime,
            hours: float, priority: str, status: str, description: str, offsets: list[int], created: datetime,
            **extra) -> ScheduledOutage:
    o = ScheduledOutage(title=title, reason=reason, mini_grid=grid, service_areas=area_list, start_at=start,
                        end_at=start + timedelta(hours=hours), priority=priority, status=status,
                        description=description, reminder_offsets=offsets, send_notice_on_publish=True,
                        created_at=created, updated_at=created, **extra)
    db.add(o)
    db.flush()
    return o


def _ctx_for(o: ScheduledOutage, **more) -> dict:
    from .services.notifications import REASON_LABELS
    return {"organization": "PowerChat Energy", "date": fmt_date(o.start_at, TZ), "start_time": fmt_time(o.start_at, TZ),
            "end_time": fmt_time(o.end_at, TZ), "reason": REASON_LABELS[o.reason], **more}


def _seed_planned(db: Session, rng: random.Random, t0: datetime, areas: dict[str, ServiceArea],
                  grids: dict[str, MiniGrid]) -> None:
    kivu, akagera = grids["Kivu Ridge Mini-Grid"], grids["Akagera Valley Mini-Grid"]
    past = [
        (58, "Quarterly line inspection", "safety_inspection", kivu, ["B"], 2),
        (47, "Inverter firmware upgrade", "network_upgrade", akagera, ["D", "E"], 1.5),
        (40, "Battery bank replacement", "equipment_replacement", kivu, ["A", "B", "C"], 4),
        (33, "Evening load shedding", "load_shedding", akagera, ["E"], 2),
        (26, "Pole replacement on School Road", "equipment_replacement", kivu, ["C"], 3),
        (18, "Distribution box maintenance", "planned_maintenance", akagera, ["D"], 2),
        (9, "Feeder breaker servicing", "planned_maintenance", kivu, ["A"], 1.5),
    ]
    for days_ago, title, reason, grid, codes, hours in past:
        start = local_dt(t0 - timedelta(days=days_ago), rng.choice([8, 9, 10, 13]))
        o = _outage(db, title=title, reason=reason, grid=grid, area_list=[areas[c] for c in codes], start=start,
                    hours=hours, priority=rng.choice(["medium", "high"]), status="completed",
                    description=f"{title} carried out by the field team.", offsets=[1440, 60],
                    created=start - timedelta(days=3), published_at=start - timedelta(days=3), customers_notified=True)
        ids = [areas[c].id for c in codes]
        _history_job(db, rng, kind="notice", template_key="scheduled_maintenance_notice", area_ids=ids,
                     send_at=start - timedelta(days=3), ctx=_ctx_for(o), outage=o)
        db.add(ActivityLog(ts=o.end_at, type="maintenance_completed", severity="success", entity_type="scheduled_outage",
                           entity_id=o.id, message=f"PO-{o.id:04d} “{title}” completed"))
        for off in (1440, 60):
            _history_job(db, rng, kind="reminder", template_key="maintenance_reminder", area_ids=ids,
                         send_at=start - timedelta(minutes=off), ctx=_ctx_for(o, time_until="24 hours" if off == 1440 else "1 hour"),
                         outage=o, offset=off)

    # One cancelled event in the past.
    start = local_dt(t0 - timedelta(days=13), 9)
    o = _outage(db, title="Transformer oil sampling", reason="safety_inspection", grid=akagera, area_list=[areas["E"]],
                start=start, hours=1, priority="low", status="cancelled", description="Postponed indefinitely.",
                offsets=[1440], created=start - timedelta(days=4), published_at=start - timedelta(days=4),
                cancelled_at=start - timedelta(days=2), cancel_reason="Contractor unavailable", customers_notified=True)
    _history_job(db, rng, kind="notice", template_key="scheduled_maintenance_notice", area_ids=[areas["E"].id],
                 send_at=start - timedelta(days=4), ctx=_ctx_for(o), outage=o)
    _history_job(db, rng, kind="cancellation", template_key="maintenance_cancelled", area_ids=[areas["E"].id],
                 send_at=start - timedelta(days=2), ctx=_ctx_for(o), outage=o)

    # Upcoming, already announced: reminders are pending in the queue.
    start = local_dt(t0 + timedelta(days=2), 9)
    o = _outage(db, title="Transformer maintenance – Market Centre", reason="planned_maintenance", grid=kivu,
                area_list=[areas["A"]], start=start, hours=2, priority="high", status="notification_queued",
                description="Routine servicing of the Market Centre step-down transformer and replacement of worn "
                            "insulators.", offsets=[1440, 60], created=t0 - timedelta(hours=5),
                published_at=t0 - timedelta(hours=4), customers_notified=True)
    _history_job(db, rng, kind="notice", template_key="scheduled_maintenance_notice", area_ids=[areas["A"].id],
                 send_at=t0 - timedelta(hours=4), ctx=_ctx_for(o), outage=o)
    db.add(ActivityLog(ts=t0 - timedelta(hours=4), type="maintenance_scheduled", entity_type="scheduled_outage", entity_id=o.id,
                       message=f"PO-{o.id:04d} “{o.title}” scheduled; notice sent in simulation"))
    for off in (1440, 60):
        db.add(NotificationJob(kind="reminder", template_key="maintenance_reminder", area_ids=[areas["A"].id],
                               send_at=start - timedelta(minutes=off), offset_minutes=off, status="scheduled",
                               scheduled_outage=o, created_at=t0 - timedelta(hours=4), context={},
                               recipients_count=sum(1 for c in areas["A"].customers if eligibility(c) is None)))

    start = local_dt(t0 + timedelta(days=5), 13)
    o = _outage(db, title="Riverside feeder network upgrade", reason="network_upgrade", grid=akagera,
                area_list=[areas["D"], areas["E"]], start=start, hours=3, priority="medium",
                status="notification_queued", description="Upgrading the Riverside feeder conductor to increase capacity "
                "for new productive-use customers.", offsets=[1440, 360], created=t0 - timedelta(days=1),
                published_at=t0 - timedelta(days=1), customers_notified=True)
    ids = [areas["D"].id, areas["E"].id]
    _history_job(db, rng, kind="notice", template_key="scheduled_maintenance_notice", area_ids=ids,
                 send_at=t0 - timedelta(days=1), ctx=_ctx_for(o), outage=o)
    db.add(ActivityLog(ts=t0 - timedelta(days=1), type="maintenance_scheduled", entity_type="scheduled_outage", entity_id=o.id,
                       message=f"PO-{o.id:04d} “{o.title}” scheduled; notice sent in simulation"))
    for off in (1440, 360):
        db.add(NotificationJob(kind="reminder", template_key="maintenance_reminder", area_ids=ids,
                               send_at=start - timedelta(minutes=off), offset_minutes=off, status="scheduled",
                               scheduled_outage=o, created_at=t0 - timedelta(days=1), context={},
                               recipients_count=sum(1 for a in ("D", "E") for c in areas[a].customers if eligibility(c) is None)))

    start = local_dt(t0 + timedelta(days=9), 10)
    db.add(ActivityLog(ts=t0 - timedelta(hours=2), type="maintenance_created", entity_type="scheduled_outage",
                       message="“Annual safety inspection – School Road” saved as draft"))
    _outage(db, title="Annual safety inspection – School Road", reason="safety_inspection", grid=kivu,
            area_list=[areas["C"]], start=start, hours=1.5, priority="low", status="draft",
            description="Annual inspection of poles, stays and earthing along School Road.", offsets=[1440, 60],
            created=t0 - timedelta(hours=2))


def _seed_readings(db: Session, rng: random.Random, t0: datetime, meters: list[Meter],
                   areas: dict[str, ServiceArea], history: list[tuple]) -> None:
    by_area: dict[int, list[Meter]] = {}
    for m in meters:
        by_area.setdefault(m.service_area_id, []).append(m)
    tz = ZoneInfo(TZ)
    step = timedelta(minutes=15)
    start = t0 - timedelta(days=7)

    def out(area_id: int, ts: datetime) -> bool:
        return any(a == area_id and s <= ts < e for a, s, e, _ in history)

    area_rows, meter_rows = [], []
    ts = start
    while ts < t0:
        local = ts.replace(tzinfo=timezone.utc).astimezone(tz)
        hour = local.hour + local.minute / 60
        for area_id, ms in by_area.items():
            dead = out(area_id, ts)
            volts, power = [], 0.0
            for m in ms:
                v = round(rng.uniform(0, 3), 1) if dead else round(min(241, max(221, rng.gauss(230, 2.5))), 1)
                kw = 0.0 if dead else round(monitoring.demand_kw(m.customer.customer_type, hour) * rng.uniform(0.85, 1.15), 3)
                volts.append(v)
                power += kw
                if ts >= t0 - timedelta(hours=24):
                    meter_rows.append(MeterReading(meter_id=m.id, ts=ts, voltage=v, power_kw=kw,
                                                   current=round(kw * 1000 / (v * 0.95), 2) if v > 50 else 0.0))
            area_rows.append(AreaReading(service_area_id=area_id, ts=ts, avg_voltage=round(sum(volts) / len(volts), 1),
                                         total_power_kw=round(power, 3), meters_reporting=len(ms),
                                         meters_no_supply=len(ms) if dead else 0))
        ts += step
    db.add_all(area_rows)
    db.add_all(meter_rows)
