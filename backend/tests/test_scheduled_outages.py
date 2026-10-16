"""Scenario A (planned maintenance) and Scenario C (rescheduling), end to end through the API."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from app.models import NotificationMessage
from app.services import notifications

from .conftest import advance, area_id, data


def iso(dt: datetime) -> str:
    return dt.replace(tzinfo=timezone.utc).isoformat()


def now(client) -> datetime:
    return datetime.fromisoformat(data(client.get("/api/demo/clock"))["now"].rstrip("Z"))


def payload(client, start_in_h=30.0, hours=2.0, offsets=(1440, 60), publish=True, area="B"):
    grid = next(g for g in data(client.get("/api/mini-grids")) if any(a["code"] == area for a in g["service_areas"]))
    start = now(client) + timedelta(hours=start_in_h)
    return {
        "title": "Line maintenance – Hillside", "reason": "planned_maintenance", "mini_grid_id": grid["id"],
        "service_area_ids": [area_id(client, area)], "start_at": iso(start), "end_at": iso(start + timedelta(hours=hours)),
        "description": "Replace worn conductors.", "priority": "high", "reminder_offsets": list(offsets),
        "send_notice_on_publish": True, "publish": publish,
    }


def test_create_publish_sends_notice_and_schedules_reminders(client):
    body = payload(client)
    o = data(client.post("/api/outages/scheduled", json=body), 201)
    assert o["status"] == "notification_queued"
    jobs = {j["kind"] + str(j["offset_minutes"] or ""): j for j in o["notifications"]}
    assert jobs["notice"]["status"] == "sent" and jobs["notice"]["sent_count"] > 0
    start = datetime.fromisoformat(o["start_at"].rstrip("Z"))
    assert datetime.fromisoformat(jobs["reminder1440"]["send_at"].rstrip("Z")) == start - timedelta(hours=24)
    assert datetime.fromisoformat(jobs["reminder60"]["send_at"].rstrip("Z")) == start - timedelta(hours=1)
    assert all(j["status"] == "scheduled" for k, j in jobs.items() if k.startswith("reminder"))


def test_notice_respects_consent(client, db):
    o = data(client.post("/api/outages/scheduled", json=payload(client)), 201)
    notice = next(j for j in o["notifications"] if j["kind"] == "notice")
    detail = data(client.get(f"/api/notifications/{notice['id']}"))
    customers = data(client.get(f"/api/customers?area_id={area_id(client, 'B')}"))
    eligible = {c["id"] for c in customers if c["notifications_eligible"]}
    assert {m["customer_id"] for m in detail["messages"]} == eligible
    assert len(eligible) < len(customers)  # some customers have no consent / are suspended
    assert all(m["simulated"] for m in detail["messages"])
    assert "Sector B – Hillside" in detail["messages"][0]["body"]


def test_validation_errors(client):
    bad = payload(client)
    bad["end_at"] = bad["start_at"]
    r = client.post("/api/outages/scheduled", json=bad)
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"
    past = payload(client, start_in_h=-1)
    assert client.post("/api/outages/scheduled", json=past).status_code == 422
    neg = payload(client, offsets=(-30,))
    r = client.post("/api/outages/scheduled", json=neg)
    assert r.status_code == 422 and "before the start" in r.json()["error"]["message"]
    wrong_area = payload(client)
    wrong_area["service_area_ids"] = [area_id(client, "D")]  # belongs to the other mini-grid
    assert client.post("/api/outages/scheduled", json=wrong_area).status_code == 422


def test_preview_shows_exact_times_and_skips_late_reminders(client):
    body = payload(client, start_in_h=5, offsets=(1440, 60), publish=False)
    p = data(client.post("/api/outages/scheduled/preview", json=body))
    reminders = {s["offset_minutes"]: s for s in p["schedule"] if s["kind"] == "reminder"}
    assert reminders[1440]["valid"] is False and reminders[60]["valid"] is True
    assert "Sector B – Hillside" in p["messages"]["notice"]["body"]
    assert p["recipients"]["eligible"] > 0 and p["simulated"] is True


def test_scenario_a_time_advance_triggers_reminder_once(client, db):
    o = data(client.post("/api/outages/scheduled", json=payload(client, start_in_h=3, offsets=(60,))), 201)
    reminder = next(j for j in o["notifications"] if j["kind"] == "reminder")
    result = data(client.post("/api/demo/advance", json={"to_next_notification": True}))
    assert result["advanced"]
    # The seeded queue may hold earlier jobs; keep jumping until ours is sent.
    for _ in range(5):
        job = data(client.get(f"/api/notifications/{reminder['id']}"))
        if job["status"] != "scheduled":
            break
        client.post("/api/demo/advance", json={"to_next_notification": True})
    assert job["status"] == "sent"
    assert "in about 1 hour" in job["messages"][0]["body"]
    count = db.scalar(select(func.count()).select_from(NotificationMessage).where(NotificationMessage.job_id == reminder["id"]))
    # Processing again must not create duplicates.
    notifications.process_due(db)
    client.post("/api/simulation/tick")
    assert db.scalar(select(func.count()).select_from(NotificationMessage)
                     .where(NotificationMessage.job_id == reminder["id"])) == count
    assert client.post("/api/notifications/simulate", json={"job_id": reminder["id"]}).status_code == 409


def test_advance_warning_never_sent_after_start(client):
    o = data(client.post("/api/outages/scheduled", json=payload(client, start_in_h=2, offsets=(60,))), 201)
    advance(client, 3 * 3600)  # jump past the start without the reminder having been processed in between
    detail = data(client.get(f"/api/outages/scheduled/{o['id']}"))
    reminder = next(j for j in detail["notifications"] if j["kind"] == "reminder")
    assert detail["status"] in ("in_progress", "completed")
    assert reminder["status"] == "cancelled"
    assert "started" in reminder["note"]


def test_scenario_c_reschedule_recalculates_and_announces(client):
    o = data(client.post("/api/outages/scheduled", json=payload(client, start_in_h=30, offsets=(1440, 60))), 201)
    old_start = datetime.fromisoformat(o["start_at"].rstrip("Z"))
    new_start = old_start + timedelta(days=2)
    r = client.patch(f"/api/outages/scheduled/{o['id']}", json={
        "start_at": iso(new_start), "end_at": iso(new_start + timedelta(hours=2)), "notify_customers": True})
    body = r.json()
    assert r.status_code == 200, r.text
    changes = body["meta"]["changes"]
    assert changes["reminders_updated"] == 2 and len(changes["announcement_job_ids"]) == 1
    updated = body["data"]
    reminders = {j["offset_minutes"]: j for j in updated["notifications"] if j["kind"] == "reminder" and j["status"] == "scheduled"}
    assert datetime.fromisoformat(reminders[1440]["send_at"].rstrip("Z")) == new_start - timedelta(hours=24)
    announcement = data(client.get(f"/api/notifications/{changes['announcement_job_ids'][0]}"))
    assert announcement["kind"] == "reschedule" and announcement["status"] == "sent"
    assert "has been rescheduled" in announcement["messages"][0]["body"]
    assert updated["reschedule_count"] == 1


def test_reschedule_closer_cancels_reminders_that_no_longer_fit(client):
    o = data(client.post("/api/outages/scheduled", json=payload(client, start_in_h=30, offsets=(1440, 60))), 201)
    sooner = now(client) + timedelta(hours=3)
    body = client.patch(f"/api/outages/scheduled/{o['id']}", json={
        "start_at": iso(sooner), "end_at": iso(sooner + timedelta(hours=1))}).json()
    assert body["meta"]["changes"]["reminders_cancelled"] == 1
    cancelled = [j for j in body["data"]["notifications"] if j["status"] == "cancelled"]
    assert cancelled and cancelled[0]["offset_minutes"] == 1440


def test_cancel_cancels_pending_and_sends_cancellation(client):
    o = data(client.post("/api/outages/scheduled", json=payload(client)), 201)
    r = client.post(f"/api/outages/scheduled/{o['id']}/cancel", json={"reason": "Crew unavailable", "notify_customers": True})
    body = r.json()
    assert body["data"]["status"] == "cancelled"
    assert body["meta"]["changes"]["pending_cancelled"] == 2
    kinds = {j["kind"]: j["status"] for j in body["data"]["notifications"]}
    assert kinds["cancellation"] == "sent"
    assert client.post(f"/api/outages/scheduled/{o['id']}/cancel", json={}).status_code == 409


def test_draft_then_publish(client):
    o = data(client.post("/api/outages/scheduled", json=payload(client, publish=False)), 201)
    assert o["status"] == "draft" and o["notifications"] == []
    pub = data(client.post(f"/api/outages/scheduled/{o['id']}/publish"))
    assert pub["status"] == "notification_queued"
    assert client.post(f"/api/outages/scheduled/{o['id']}/publish").status_code == 409


def test_planned_outage_in_progress_suppresses_incident(client):
    o = data(client.post("/api/outages/scheduled", json=payload(client, start_in_h=0.05, offsets=())), 201)
    advance(client, 200)
    for _ in range(4):
        client.post("/api/simulation/tick")
    dash = data(client.get("/api/dashboard"))
    area = next(a for a in dash["areas"] if a["code"] == "B")
    assert area["planned_outage"]["id"] == o["id"]
    assert area["meters_no_supply"] > 0
    assert all(i["service_area_id"] != area["id"] for i in dash["active_incidents"])
    activity = data(client.get("/api/activity?limit=100"))
    assert any(a["type"] == "detection_suppressed" for a in activity)
