"""Meter simulation and rule-based unexpected-outage detection.

Per meter (debounced):
    voltage <  outage_voltage_max   -> no_supply
    voltage <  low_voltage_max      -> low_voltage
    otherwise                       -> normal
    in no_supply, voltage must reach restore_voltage_min to leave it (hysteresis)
    a status must be seen `confirm_readings` times in a row before it is accepted
    no reading for `stale_after_seconds` -> offline (communication problem, NOT an outage)

Per service area:
    1 meter without supply                -> low-severity *meter* incident (possible customer-side
                                             fault; never an automatic community-wide alert)
    >= min_meters_for_area_outage meters  -> *area* incident, auto-confirmed after
                                             `verification_seconds` of persisting evidence
    area under an in-progress planned outage -> no incident (expected interruption)
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..models import AreaReading, Incident, IncidentEvent, Meter, MeterReading, ServiceArea
from . import activity, incidents, scheduled_outages, settings_store
from .settings_store import DetectionSettings
from .timefmt import to_local

SCENARIOS = ("no_supply", "low_voltage", "comm_loss")
READING_PERSIST_SECONDS = 30
AREA_PERSIST_SECONDS = 15
ESSENTIAL_TYPES = {"essential_service"}

# Typical demand (kW) by customer type and local hour.
_PROFILES = {
    "residential": lambda h: 0.12 + 0.55 * math.exp(-((h - 19.5) ** 2) / 4) + 0.15 * math.exp(-((h - 7) ** 2) / 2),
    "commercial": lambda h: 0.2 + (1.4 if 8 <= h < 20 else 0.0) + 0.4 * math.exp(-((h - 18) ** 2) / 3),
    "productive_use": lambda h: 0.3 + (3.2 if 8 <= h < 17 else 0.0),
    "public_institution": lambda h: 0.25 + (1.8 if 7 <= h < 17 else 0.0),
    "essential_service": lambda h: 1.1 + 0.6 * math.exp(-((h - 12) ** 2) / 10),
}
_NO_METER_FACTOR = 1.0

_rng = random.Random()
_last_area_persist: dict[int, datetime] = {}
_suppression_logged: set[tuple[int, int]] = set()


@dataclass
class Transition:
    meter: Meter
    previous: str
    current: str


def seed_rng(seed: int | None) -> None:
    _rng.seed(seed)


def reset_state() -> None:
    _last_area_persist.clear()
    _suppression_logged.clear()


def demand_kw(customer_type: str, hour: float) -> float:
    return _PROFILES.get(customer_type, _PROFILES["residential"])(hour)


# ---------------------------------------------------------------- detection
def classify(voltage: float, cfg: DetectionSettings) -> str:
    if voltage < cfg.outage_voltage_max:
        return "no_supply"
    if voltage < cfg.low_voltage_max:
        return "low_voltage"
    return "normal"


def evaluate(meter: Meter, voltage: float, cfg: DetectionSettings, t: datetime) -> Transition | None:
    """Update the meter's persisted detector state with a reading; return a confirmed transition."""
    if meter.status == "no_supply" and voltage < cfg.restore_voltage_min:
        target = "no_supply"
    else:
        target = classify(voltage, cfg)
    if target == meter.status:
        meter.pending_status, meter.pending_count, meter.pending_since = None, 0, None
        return None
    if target == meter.pending_status:
        meter.pending_count += 1
    else:
        meter.pending_status, meter.pending_count, meter.pending_since = target, 1, t
    # A meter that was offline has just proven it can communicate: accept its state immediately.
    if meter.pending_count >= cfg.confirm_readings or meter.status == "offline":
        tr = Transition(meter, meter.status, target)
        meter.status, meter.status_since = target, (meter.pending_since or t)
        meter.pending_status, meter.pending_count, meter.pending_since = None, 0, None
        return tr
    return None


# --------------------------------------------------------------- simulation
def _voltage(scenario: str | None) -> float:
    if scenario in ("no_supply", "planned_outage"):
        return round(_rng.uniform(0.0, 3.0), 1)
    if scenario == "low_voltage":
        return round(_rng.uniform(182.0, 192.0), 1)
    return round(min(241.0, max(221.0, _rng.gauss(230.0, 2.5))), 1)


def simulate_tick(db: Session, t: datetime) -> list[Transition]:
    cfg = settings_store.get_section(db, "detection")
    tz = settings_store.get_section(db, "general").timezone
    hour = to_local(t, tz).hour + to_local(t, tz).minute / 60
    planned = scheduled_outages.areas_under_planned_outage(db, t)
    meters = db.scalars(select(Meter).options(selectinload(Meter.customer), selectinload(Meter.service_area))).all()
    transitions: list[Transition] = []
    changed_areas: set[int] = set()

    for m in meters:
        scenario = m.sim_scenario or m.service_area.sim_scenario
        if scenario is None and m.service_area_id in planned:
            scenario = "planned_outage"
        if scenario == "comm_loss":
            continue
        v = _voltage(scenario)
        ctype = m.customer.customer_type if m.customer else "residential"
        kw = 0.0 if v < cfg.outage_voltage_max else round(demand_kw(ctype, hour) * _rng.uniform(0.85, 1.15), 3)
        if scenario == "low_voltage":
            kw = round(kw * 0.8, 3)
        current = round(kw * 1000 / (v * 0.95), 2) if v >= cfg.outage_voltage_max else 0.0
        m.last_voltage, m.last_current, m.last_power_kw, m.last_reading_at = v, current, kw, t
        tr = evaluate(m, v, cfg, t)
        if tr:
            transitions.append(tr)
            changed_areas.add(m.service_area_id)
        if tr or m.last_persisted_at is None or (t - m.last_persisted_at).total_seconds() >= READING_PERSIST_SECONDS:
            db.add(MeterReading(meter_id=m.id, ts=t, voltage=v, current=current, power_kw=kw))
            m.last_persisted_at = t

    stale_before = t - timedelta(seconds=cfg.stale_after_seconds)
    for m in meters:
        if m.status in ("normal", "low_voltage") and m.last_reading_at is not None and m.last_reading_at < stale_before:
            transitions.append(Transition(m, m.status, "offline"))
            m.status, m.status_since = "offline", t
            m.pending_status, m.pending_count, m.pending_since = None, 0, None
            changed_areas.add(m.service_area_id)

    for tr in transitions:
        m = tr.meter
        if tr.current == "offline":
            activity.log(db, "meter_offline", f"Meter {m.serial} stopped reporting: possible communication problem "
                         "(not treated as an outage)", severity="warning", entity_type="meter", entity_id=m.id, ts=t)
        elif tr.previous == "offline":
            activity.log(db, "meter_online", f"Meter {m.serial} is reporting again", entity_type="meter",
                         entity_id=m.id, ts=t)
        elif tr.current == "low_voltage":
            activity.log(db, "low_voltage", f"Low voltage ({m.last_voltage:.0f} V) on meter {m.serial}",
                         severity="warning", entity_type="meter", entity_id=m.id, ts=t)

    _record_area_readings(db, meters, t, changed_areas)
    db.flush()
    return transitions


def _record_area_readings(db: Session, meters: list[Meter], t: datetime, changed: set[int]) -> None:
    by_area: dict[int, list[Meter]] = {}
    for m in meters:
        by_area.setdefault(m.service_area_id, []).append(m)
    for area_id, ms in by_area.items():
        last = _last_area_persist.get(area_id)
        if area_id not in changed and last is not None and (t - last).total_seconds() < AREA_PERSIST_SECONDS:
            continue
        reporting = [m for m in ms if m.status != "offline" and m.last_voltage is not None]
        db.add(AreaReading(
            service_area_id=area_id, ts=t,
            avg_voltage=round(sum(m.last_voltage for m in reporting) / len(reporting), 1) if reporting else None,
            total_power_kw=round(sum(m.last_power_kw or 0 for m in reporting), 3),
            meters_reporting=len(reporting),
            meters_no_supply=sum(1 for m in ms if m.status == "no_supply"),
        ))
        _last_area_persist[area_id] = t


# ---------------------------------------------------------------- incidents
def _severity(area: ServiceArea, affected: list[Meter], scope: str) -> str:
    if scope == "meter":
        return "low"
    ratio = len(affected) / max(1, len(area.meters))
    if ratio < 0.5:
        return "medium"
    if ratio >= 0.8 and any(c.customer_type in ESSENTIAL_TYPES for c in area.customers):
        return "critical"
    return "high"


def _estimate_customers(area: ServiceArea, affected: list[Meter]) -> int:
    """Not every customer has a smart meter: extrapolate from the share of metered customers affected."""
    if not area.meters:
        return 0
    return max(len(affected), round(len(area.customers) * len(affected) / len(area.meters)))


def incidents_tick(db: Session, t: datetime) -> None:
    cfg = settings_store.get_section(db, "detection")
    planned = scheduled_outages.areas_under_planned_outage(db, t)
    areas = db.scalars(select(ServiceArea).options(selectinload(ServiceArea.meters),
                                                   selectinload(ServiceArea.customers))).all()
    for area in areas:
        affected = [m for m in area.meters if m.status == "no_supply"]
        latest = db.scalar(select(Incident).where(Incident.service_area_id == area.id, Incident.is_seed.is_(False))
                           .order_by(Incident.id.desc()).limit(1))
        open_inc = latest if latest and latest.resolution_status != "resolved" else None
        rejected_live = latest if latest and latest.verification_status == "rejected" and latest.power_restored_at is None else None

        if affected:
            if area.id in planned:
                outage = planned[area.id]
                if (outage.id, area.id) not in _suppression_logged:
                    _suppression_logged.add((outage.id, area.id))
                    activity.log(db, "detection_suppressed",
                                 f"Voltage loss in {area.name} matches planned interruption "
                                 f"{scheduled_outages.code(outage)}: no incident raised", entity_type="scheduled_outage",
                                 entity_id=outage.id, ts=t)
                continue
            if rejected_live is not None:
                continue  # operator rejected this event; wait for supply to return before re-alerting
            scope = "area" if len(affected) >= cfg.min_meters_for_area_outage else "meter"
            if open_inc is None:
                open_inc = _create_incident(db, area, affected, scope, t)
            else:
                _update_incident(db, open_inc, area, affected, scope, t)
            if (open_inc.verification_status == "potential" and open_inc.scope == "area" and cfg.auto_confirm
                    and len(affected) >= cfg.min_meters_for_area_outage
                    and (t - open_inc.detected_at).total_seconds() >= cfg.verification_seconds):
                notify = settings_store.get_section(db, "notifications").auto_notify_unexpected
                incidents.confirm(db, open_inc, method="auto", actor="system", notify_customers=notify,
                                  note=f"{len(affected)} of {len(area.meters)} meters without supply for "
                                       f"{int((t - open_inc.detected_at).total_seconds())}s")
        else:
            if rejected_live is not None:
                rejected_live.power_restored_at = t
            if open_inc is not None and open_inc.power_restored_at is None:
                _restored(db, open_inc, cfg, t)
    db.flush()


def _create_incident(db: Session, area: ServiceArea, affected: list[Meter], scope: str, t: datetime) -> Incident:
    evidence = [m.status_since for m in affected if m.status_since] or [t]
    inc = Incident(service_area_id=area.id, scope=scope, severity=_severity(area, affected, scope),
                   verification_status="potential", resolution_status="open", detected_at=t,
                   first_evidence_at=min(evidence), affected_meter_ids=[m.id for m in affected],
                   peak_affected_meters=len(affected), estimated_customers=_estimate_customers(area, affected),
                   created_at=t)
    db.add(inc)
    db.flush()
    msg = f"Potential outage detected: {len(affected)} of {len(area.meters)} meters in {area.name} report no supply"
    db.add(IncidentEvent(incident_id=inc.id, ts=t, type="detected", message=msg))
    if scope == "meter":
        db.add(IncidentEvent(incident_id=inc.id, ts=t, type="note",
                             message="Single meter affected: treated as a possible local fault, not a community-wide "
                                     "outage. No customer broadcast."))
    activity.log(db, "outage_detected", f"{incidents.code(inc)}: {msg}",
                 severity="critical" if scope == "area" else "warning", entity_type="incident", entity_id=inc.id,
                 operator_alert=True, ts=t)
    return inc


def _update_incident(db: Session, inc: Incident, area: ServiceArea, affected: list[Meter], scope: str,
                     t: datetime) -> None:
    ids = [m.id for m in affected]
    if inc.power_restored_at is not None:
        inc.power_restored_at = None
        db.add(IncidentEvent(incident_id=inc.id, ts=t, type="supply_lost", message="Supply lost again"))
    if set(ids) != set(inc.affected_meter_ids):
        direction = "increased" if len(ids) > len(inc.affected_meter_ids) else "decreased"
        db.add(IncidentEvent(incident_id=inc.id, ts=t, type="evidence",
                             message=f"Affected meters {direction} to {len(ids)} of {len(area.meters)}"))
        inc.affected_meter_ids = ids
    if scope == "area" and inc.scope == "meter":
        inc.scope = "area"
        db.add(IncidentEvent(incident_id=inc.id, ts=t, type="escalated",
                             message="Multiple meters affected: escalated to a service-area outage"))
        activity.log(db, "outage_escalated", f"{incidents.code(inc)} escalated to a service-area outage in {area.name}",
                     severity="critical", entity_type="incident", entity_id=inc.id, operator_alert=True, ts=t)
    inc.peak_affected_meters = max(inc.peak_affected_meters, len(ids))
    inc.severity = _severity(area, affected, inc.scope) if _rank(_severity(area, affected, inc.scope)) > _rank(inc.severity) else inc.severity
    inc.estimated_customers = max(inc.estimated_customers, _estimate_customers(area, affected))


def _rank(sev: str) -> int:
    return ["low", "medium", "high", "critical"].index(sev)


def _restored(db: Session, inc: Incident, cfg: DetectionSettings, t: datetime) -> None:
    inc.power_restored_at = t
    inc.affected_meter_ids = []
    db.add(IncidentEvent(incident_id=inc.id, ts=t, type="power_restored",
                         message="Power restored: all meters report normal voltage"))
    if inc.verification_status == "potential":
        incidents.close(db, inc, t, note="Supply returned before the outage was confirmed (transient event). "
                                         "No customer message sent.")
    elif cfg.auto_resolve_on_restore:
        incidents.close(db, inc, t, note="Power restored; incident closed automatically. No restoration message sent "
                                         "automatically.")
    else:
        activity.log(db, "power_restored", f"Power restored for {incidents.code(inc)}; awaiting operator resolution",
                     severity="success", entity_type="incident", entity_id=inc.id, ts=t)
