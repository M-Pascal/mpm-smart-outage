"""Dashboard, monitoring, simulation, demo controls, settings, analytics, search."""
from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from .. import serializers as S
from ..clock import CLOCK, iso
from ..clock import now as clock_now
from ..db import WRITE_LOCK
from ..errors import AppError, invalid, not_found, ok
from ..channels.router import get_router
from ..integrations import mpm
from ..models import (
    ActivityLog, Customer, Incident, Meter, MiniGrid, NotificationJob, ScheduledOutage, ServiceArea,
)
from ..services import analytics as analytics_svc
from ..services import engine, scheduled_outages, settings_store
from ..services.notifications import audience
from .deps import get_db

router = APIRouter(prefix="/api")

ACTIVE_PLANNED = ("scheduled", "notification_queued", "in_progress")


# ------------------------------------------------------------------ health
@router.get("/health")
def health(db: Session = Depends(get_db)):
    return ok({"status": "ok", "time": iso(clock_now()), "clock_offset_seconds": CLOCK.offset.total_seconds()})


# --------------------------------------------------------------- dashboard
def _area_stats(db: Session) -> list[dict]:
    areas = db.scalars(select(ServiceArea).options(selectinload(ServiceArea.meters), selectinload(ServiceArea.customers),
                                                   selectinload(ServiceArea.mini_grid)).order_by(ServiceArea.code)).all()
    planned = scheduled_outages.areas_under_planned_outage(db, clock_now())
    open_incidents = {i.service_area_id: i for i in db.scalars(select(Incident).where(
        Incident.resolution_status != "resolved", Incident.verification_status != "rejected"))}
    out = []
    for a in areas:
        reporting = [m for m in a.meters if m.status != "offline" and m.last_voltage is not None]
        powered = [m for m in reporting if m.status != "no_supply"]
        inc = open_incidents.get(a.id)
        out.append(S.area(a, {
            "customer_count": len(a.customers), "meter_count": len(a.meters),
            "meters_online": len(reporting), "meters_offline": len(a.meters) - len(reporting),
            "meters_no_supply": sum(1 for m in a.meters if m.status == "no_supply"),
            "meters_low_voltage": sum(1 for m in a.meters if m.status == "low_voltage"),
            "avg_voltage": round(sum(m.last_voltage for m in powered) / len(powered), 1) if powered else None,
            "total_power_kw": round(sum(m.last_power_kw or 0 for m in reporting), 2),
            "planned_outage": {"id": planned[a.id].id, "code": scheduled_outages.code(planned[a.id]),
                               "title": planned[a.id].title} if a.id in planned else None,
            "open_incident": {"id": inc.id, "code": f"INC-{inc.id:04d}", "severity": inc.severity,
                              "verification_status": inc.verification_status} if inc else None,
        }))
    return out


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db)):
    t = clock_now()
    meters = db.scalars(select(Meter)).all()
    areas = _area_stats(db)
    open_incidents = db.scalars(select(Incident).where(Incident.resolution_status != "resolved",
                                                       Incident.verification_status != "rejected")
                                .order_by(Incident.detected_at.desc())).all()
    upcoming = db.scalars(select(ScheduledOutage).where(ScheduledOutage.status.in_(ACTIVE_PLANNED + ("draft",)),
                                                        ScheduledOutage.end_at > t)
                          .order_by(ScheduledOutage.start_at).limit(6)).all()
    in_progress_customers = sum(a["customer_count"] for a in areas if a["planned_outage"])
    reporting = [m for m in meters if m.status != "offline" and m.last_voltage is not None]
    powered = [m for m in reporting if m.status != "no_supply"]
    summary = {
        "total_meters": len(meters),
        "active_meters": len(reporting),
        "offline_meters": len(meters) - len(reporting),
        "meters_no_supply": sum(1 for m in meters if m.status == "no_supply"),
        "scheduled_interruptions": db.scalar(select(func.count()).select_from(ScheduledOutage).where(
            ScheduledOutage.status.in_(ACTIVE_PLANNED), ScheduledOutage.end_at > t)),
        "planned_in_progress": sum(1 for a in areas if a["planned_outage"]),
        "unexpected_outages": len(open_incidents),
        "unconfirmed_incidents": sum(1 for i in open_incidents if i.verification_status == "potential"),
        "customers_affected": sum(i.estimated_customers for i in open_incidents if i.power_restored_at is None)
                              + in_progress_customers,
        "notifications_scheduled": db.scalar(select(func.count()).select_from(NotificationJob).where(
            NotificationJob.status == "scheduled")),
        "avg_voltage": round(sum(m.last_voltage for m in powered) / len(powered), 1) if powered else None,
        "total_power_kw": round(sum(m.last_power_kw or 0 for m in reporting), 2),
        "total_customers": db.scalar(select(func.count()).select_from(Customer)),
    }
    activity = db.scalars(select(ActivityLog).order_by(ActivityLog.ts.desc(), ActivityLog.id.desc()).limit(15)).all()
    return ok({
        "generated_at": iso(t),
        "summary": summary,
        "areas": areas,
        "upcoming_maintenance": [S.scheduled_outage(o, db) for o in upcoming],
        "active_incidents": [S.incident(i, db) for i in open_incidents],
        "recent_activity": [S.activity_entry(a) for a in activity],
        "simulated": True,
    })


# --------------------------------------------------------- grid & meters
@router.get("/mini-grids")
def list_mini_grids(db: Session = Depends(get_db)):
    return ok([S.mini_grid(g) for g in db.scalars(select(MiniGrid).order_by(MiniGrid.name))])


@router.get("/areas")
def list_areas(db: Session = Depends(get_db)):
    return ok(_area_stats(db))


class AreaIn(BaseModel):
    code: str = Field(min_length=1, max_length=10)
    name: str = Field(min_length=2, max_length=120)
    description: str = Field("", max_length=500)
    mini_grid_id: int


class AreaPatch(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=120)
    description: Optional[str] = Field(None, max_length=500)


@router.post("/areas", status_code=201)
def create_area(body: AreaIn, db: Session = Depends(get_db)):
    with WRITE_LOCK:
        if db.get(MiniGrid, body.mini_grid_id) is None:
            raise invalid("select a valid mini-grid", "mini_grid_id")
        if db.scalar(select(ServiceArea).where(ServiceArea.code == body.code.upper())):
            raise invalid(f"area code {body.code.upper()} is already used", "code")
        area = ServiceArea(code=body.code.upper(), name=body.name, description=body.description,
                           mini_grid_id=body.mini_grid_id)
        db.add(area)
        db.commit()
        return ok(S.area(area, {"customer_count": 0, "meter_count": 0}))


@router.patch("/areas/{area_id}")
def update_area(area_id: int, body: AreaPatch, db: Session = Depends(get_db)):
    with WRITE_LOCK:
        area = db.get(ServiceArea, area_id) or _raise(not_found("Service area", area_id))
        for k, v in body.model_dump(exclude_unset=True).items():
            if v is not None:
                setattr(area, k, v)
        db.commit()
        return ok(S.area(area))


def _raise(err: AppError):
    raise err


@router.get("/meters")
def list_meters(area_id: Optional[int] = None, status: Optional[str] = None, q: Optional[str] = None,
                db: Session = Depends(get_db)):
    query = select(Meter).options(selectinload(Meter.customer), selectinload(Meter.service_area)).order_by(Meter.serial)
    if area_id:
        query = query.where(Meter.service_area_id == area_id)
    if status:
        query = query.where(Meter.status == status)
    meters = [S.meter(m) for m in db.scalars(query)]
    if q:
        ql = q.lower()
        meters = [m for m in meters if ql in m["serial"].lower() or ql in (m["customer_name"] or "").lower()]
    return ok(meters)


@router.get("/meters/{meter_id}")
def get_meter(meter_id: int, db: Session = Depends(get_db)):
    m = db.get(Meter, meter_id) or _raise(not_found("Meter", meter_id))
    return ok(S.meter(m))


@router.get("/meters/{meter_id}/readings")
def meter_readings(meter_id: int, range: Literal["1h", "6h", "24h", "7d"] = "24h", db: Session = Depends(get_db)):
    db.get(Meter, meter_id) or _raise(not_found("Meter", meter_id))
    return ok(analytics_svc.meter_series(db, meter_id, range), simulated=True)


@router.get("/monitoring/series")
def monitoring_series(range: Literal["1h", "6h", "24h", "7d"] = "6h", area_id: Optional[int] = None,
                      db: Session = Depends(get_db)):
    return ok(analytics_svc.series(db, range, area_id), range=range, simulated=True)


# -------------------------------------------------------------- simulation
class SimOutageIn(BaseModel):
    scenario: Literal["voltage_loss", "multi_meter_loss", "comm_failure", "low_voltage"]
    service_area_id: Optional[int] = None
    meter_id: Optional[int] = None


class SimRestoreIn(BaseModel):
    service_area_id: Optional[int] = None
    meter_id: Optional[int] = None


@router.post("/simulation/outage")
def simulate_outage(body: SimOutageIn, db: Session = Depends(get_db)):
    with WRITE_LOCK:
        meter = db.get(Meter, body.meter_id) if body.meter_id else None
        area = db.get(ServiceArea, body.service_area_id) if body.service_area_id else None
        if body.meter_id and meter is None:
            raise not_found("Meter", body.meter_id)
        if body.service_area_id and area is None:
            raise not_found("Service area", body.service_area_id)
        scenario = {"voltage_loss": "no_supply", "multi_meter_loss": "no_supply", "comm_failure": "comm_loss",
                    "low_voltage": "low_voltage"}[body.scenario]
        if body.scenario == "multi_meter_loss":
            if area is None:
                raise invalid("choose a service area for a multi-meter outage", "service_area_id")
            area.sim_scenario = scenario
            target = area.name
        elif meter is not None:
            meter.sim_scenario = scenario
            target = f"meter {meter.serial}"
        elif area is not None and body.scenario in ("comm_failure", "low_voltage"):
            area.sim_scenario = scenario
            target = area.name
        elif area is not None:
            meter = db.scalar(select(Meter).where(Meter.service_area_id == area.id).order_by(Meter.serial))
            if meter is None:
                raise invalid("this service area has no meters", "service_area_id")
            meter.sim_scenario = scenario
            target = f"meter {meter.serial}"
        else:
            raise invalid("choose a meter or a service area", "meter_id")
        db.commit()
        engine.tick(db)  # first reading immediately so the dashboard reacts at once
        return ok({"scenario": body.scenario, "target": target, "simulated": True})


@router.post("/simulation/restore")
def simulate_restore(body: SimRestoreIn = SimRestoreIn(), db: Session = Depends(get_db)):
    with WRITE_LOCK:
        if body.meter_id:
            m = db.get(Meter, body.meter_id) or _raise(not_found("Meter", body.meter_id))
            m.sim_scenario = None
        elif body.service_area_id:
            a = db.get(ServiceArea, body.service_area_id) or _raise(not_found("Service area", body.service_area_id))
            a.sim_scenario = None
            for m in a.meters:
                m.sim_scenario = None
        else:
            for a in db.scalars(select(ServiceArea)):
                a.sim_scenario = None
            for m in db.scalars(select(Meter)):
                m.sim_scenario = None
        db.commit()
        engine.tick(db)
        return ok({"restored": True})


@router.post("/simulation/normal")
def simulate_normal(db: Session = Depends(get_db)):
    return simulate_restore(SimRestoreIn(), db)


@router.post("/simulation/tick")
def simulate_tick(count: int = Query(1, ge=1, le=20), db: Session = Depends(get_db)):
    result = {}
    for _ in range(count):
        result = engine.tick(db)
    return ok({"ticks": count, "notifications_sent": result.get("notifications_sent", 0)})


@router.get("/simulation/state")
def simulation_state(db: Session = Depends(get_db)):
    return ok({
        "areas": [{"id": a.id, "name": a.name, "scenario": a.sim_scenario} for a in db.scalars(select(ServiceArea))],
        "meters": [{"id": m.id, "serial": m.serial, "scenario": m.sim_scenario}
                   for m in db.scalars(select(Meter).where(Meter.sim_scenario.is_not(None)))],
        "auto_tick": settings_store.get_section(db, "demo").auto_tick,
    })


# --------------------------------------------------------------- demo mode
class AdvanceIn(BaseModel):
    minutes: Optional[float] = Field(None, gt=0, le=60 * 24 * 30)
    to_next_notification: bool = False


@router.get("/demo/clock")
def demo_clock(db: Session = Depends(get_db)):
    nxt = engine.next_scheduled_job(db)
    return ok({"now": iso(clock_now()), "offset_seconds": CLOCK.offset.total_seconds(),
               "auto_tick": settings_store.get_section(db, "demo").auto_tick,
               "next_notification": S.job(nxt) if nxt else None})


@router.post("/demo/advance")
def demo_advance(body: AdvanceIn, db: Session = Depends(get_db)):
    if body.to_next_notification:
        result = engine.advance_to_next_notification(db)
    elif body.minutes:
        result = {"advanced": True, **engine.advance(db, body.minutes)}
    else:
        raise invalid("provide minutes or to_next_notification", "minutes")
    result.pop("at", None)
    return ok({**result, "now": iso(clock_now()), "offset_seconds": CLOCK.offset.total_seconds()})


@router.post("/demo/clock/reset")
def demo_clock_reset(db: Session = Depends(get_db)):
    engine.set_clock_offset(db, 0)
    return ok({"now": iso(clock_now()), "offset_seconds": 0})


class AutoTickIn(BaseModel):
    enabled: bool


@router.post("/demo/auto-tick")
def demo_auto_tick(body: AutoTickIn, db: Session = Depends(get_db)):
    with WRITE_LOCK:
        settings_store.update_section(db, "demo", {"auto_tick": body.enabled})
        db.commit()
    return ok({"auto_tick": body.enabled})


@router.post("/demo/reset")
def demo_reset(request: Request):
    request.app.state.reset_database()
    return ok({"reset": True})


# ---------------------------------------------------------------- activity
@router.get("/activity")
def list_activity(limit: int = Query(50, ge=1, le=300), alerts_only: bool = False, db: Session = Depends(get_db)):
    q = select(ActivityLog).order_by(ActivityLog.ts.desc(), ActivityLog.id.desc()).limit(limit)
    if alerts_only:
        q = q.where(ActivityLog.operator_alert.is_(True))
    unread = db.scalar(select(func.count()).select_from(ActivityLog).where(ActivityLog.operator_alert.is_(True),
                                                                          ActivityLog.read.is_(False)))
    return ok([S.activity_entry(a) for a in db.scalars(q)], unread_alerts=unread)


@router.post("/activity/read-all")
def mark_all_read(db: Session = Depends(get_db)):
    with WRITE_LOCK:
        for a in db.scalars(select(ActivityLog).where(ActivityLog.read.is_(False))):
            a.read = True
        db.commit()
    return ok({"read": True})


# ------------------------------------------------------------------ search
@router.get("/search")
def search(q: str = Query(..., min_length=1, max_length=80), db: Session = Depends(get_db)):
    like = f"%{q}%"
    customers = db.scalars(select(Customer).where(or_(Customer.name.ilike(like), Customer.phone.ilike(like))).limit(5)).all()
    meters = db.scalars(select(Meter).where(Meter.serial.ilike(like)).limit(5)).all()
    outages = db.scalars(select(ScheduledOutage).where(ScheduledOutage.title.ilike(like)).limit(5)).all()
    areas = db.scalars(select(ServiceArea).where(ServiceArea.name.ilike(like)).limit(5)).all()
    results = (
        [{"type": "customer", "id": c.id, "title": c.name, "subtitle": f"CUS-{c.id:04d} · {c.service_area.name}"} for c in customers]
        + [{"type": "meter", "id": m.id, "title": m.serial, "subtitle": m.service_area.name} for m in meters]
        + [{"type": "scheduled_outage", "id": o.id, "title": o.title, "subtitle": f"{scheduled_outages.code(o)} · {o.status}"} for o in outages]
        + [{"type": "service_area", "id": a.id, "title": a.name, "subtitle": a.mini_grid.name} for a in areas]
    )
    up = q.upper().strip()
    if up.startswith("INC-") and up[4:].isdigit():
        inc = db.get(Incident, int(up[4:]))
        if inc:
            results.insert(0, {"type": "incident", "id": inc.id, "title": f"INC-{inc.id:04d}", "subtitle": inc.service_area.name})
    if up.startswith("PO-") and up[3:].isdigit():
        o = db.get(ScheduledOutage, int(up[3:]))
        if o:
            results.insert(0, {"type": "scheduled_outage", "id": o.id, "title": o.title, "subtitle": scheduled_outages.code(o)})
    return ok(results)


# ---------------------------------------------------------------- settings
@router.get("/settings")
def get_settings(request: Request, db: Session = Depends(get_db)):
    return ok({**settings_store.get_all(db), "environment": _integrations(request)})


@router.put("/settings/{section}")
def put_settings(section: Literal["general", "notifications", "detection"], values: dict, db: Session = Depends(get_db)):
    with WRITE_LOCK:
        try:
            updated = settings_store.update_section(db, section, values)
        except ValueError as exc:
            msg = exc.errors()[0]["msg"] if hasattr(exc, "errors") else str(exc)
            field = ".".join(str(x) for x in exc.errors()[0]["loc"]) if hasattr(exc, "errors") else None
            raise invalid(msg.removeprefix("Value error, "), field)
        db.commit()
        return ok(updated.model_dump())


def _integrations(request: Request) -> dict:
    return {"whatsapp": get_router().status(), "mpm": mpm.status(request.app.state.config)}


# --------------------------------------------------------------- analytics
@router.get("/analytics")
def get_analytics(days: int = Query(90, ge=7, le=365), db: Session = Depends(get_db)):
    return ok(analytics_svc.analytics(db, days))


@router.get("/audience")
def get_audience(area_ids: str = Query(..., description="Comma-separated service area ids"), detail: bool = False,
                 db: Session = Depends(get_db)):
    ids = [int(x) for x in area_ids.split(",") if x.strip().isdigit()]
    aud = audience(db, ids)
    result = {"eligible": len(aud["eligible"]), "total_in_areas": len(aud["customers"]), "excluded": aud["excluded"]}
    if detail:
        router = get_router()
        rows = []
        for c in aud["customers"]:
            route = router.route(c)
            rows.append({"id": c.id, "name": c.name, "phone": S.mask_phone(c.phone), "service_area_name": c.service_area.name,
                         "source": c.source, "included": route.excluded_reason is None,
                         "reason": route.excluded_reason or route.blocked_reason,
                         "channel": route.channel.channel if route.channel else None,
                         "simulated": route.channel.simulated if route.channel else None})
        result["customers"] = rows
    return ok(result)
