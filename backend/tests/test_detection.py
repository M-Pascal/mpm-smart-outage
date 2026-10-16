from datetime import datetime, timedelta

from app.models import Meter
from app.services.monitoring import classify, evaluate
from app.services.scheduled_outages import plan_notifications
from app.services.settings_store import DetectionSettings
from app.services.templates import render, unknown_placeholders
from app.services.timefmt import fmt_minutes

CFG = DetectionSettings()
T = datetime(2026, 10, 20, 7, 0)


def meter(status="normal") -> Meter:
    return Meter(serial="X", service_area_id=1, status=status, pending_count=0)


def test_classify():
    assert classify(0, CFG) == "no_supply"
    assert classify(120, CFG) == "low_voltage"
    assert classify(230, CFG) == "normal"


def test_requires_consecutive_readings_and_ignores_glitch():
    m = meter()
    assert evaluate(m, 1.0, CFG, T) is None and m.pending_status == "no_supply"
    assert evaluate(m, 230, CFG, T) is None and m.status == "normal" and m.pending_status is None
    evaluate(m, 1.0, CFG, T)
    tr = evaluate(m, 0.5, CFG, T + timedelta(seconds=3))
    assert tr.previous == "normal" and tr.current == "no_supply"
    assert m.status_since == T  # evidence started at the first bad reading


def test_restoration_hysteresis():
    m = meter("no_supply")
    for _ in range(3):
        assert evaluate(m, 150, CFG, T) is None  # above outage threshold, below restore threshold
    assert m.status == "no_supply"
    evaluate(m, 229, CFG, T)
    assert evaluate(m, 231, CFG, T).current == "normal"


def test_offline_meter_recovers_on_first_reading():
    m = meter("offline")
    assert evaluate(m, 230, CFG, T).current == "normal"


def test_plan_never_schedules_advance_warning_after_start():
    start = T + timedelta(hours=10)
    plan = plan_notifications(start, [1440, 360, 60], True, T)
    by_offset = {p["offset_minutes"]: p for p in plan}
    assert by_offset[1440]["valid"] is False and "Skipped" in by_offset[1440]["reason"]
    assert by_offset[360]["valid"] and by_offset[360]["send_at"] == start - timedelta(hours=6)
    assert by_offset[60]["valid"]
    assert all(p["send_at"] < start for p in plan if p["valid"])
    assert plan[0]["kind"] == "notice"


def test_templates_and_formatting():
    assert render("Hi {area}, {missing}", {"area": "Sector A"}) == "Hi Sector A, {missing}"
    assert unknown_placeholders("{area} {bogus}") == ["bogus"]
    assert fmt_minutes(1440) == "1 day" and fmt_minutes(90) == "1 hour 30 minutes" and fmt_minutes(60) == "1 hour"
