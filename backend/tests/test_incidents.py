"""Scenario B (unexpected outage) and detection rules, end to end."""
from .conftest import advance, area_id, data


def active_incident(client, area):
    return next((i for i in data(client.get("/api/incidents?status=active")) if i["service_area_id"] == area), None)


def test_normal_supply_has_no_incidents(client):
    for _ in range(3):
        client.post("/api/simulation/tick")
    dash = data(client.get("/api/dashboard"))
    assert dash["summary"]["unexpected_outages"] == 0
    assert dash["summary"]["active_meters"] == dash["summary"]["total_meters"]


def test_single_meter_is_not_a_community_alert(client):
    a = area_id(client, "C")
    data(client.post("/api/simulation/outage", json={"scenario": "voltage_loss", "service_area_id": a}))
    for _ in range(2):
        client.post("/api/simulation/tick")
    advance(client, 30)
    inc = active_incident(client, a)
    assert inc is not None and inc["scope"] == "meter" and inc["severity"] == "low"
    assert inc["verification_status"] == "potential"  # never auto-confirmed
    assert data(client.get(f"/api/incidents/{inc['id']}"))["notifications"] == []


def test_scenario_b_detect_confirm_notify_restore_without_message(client):
    a = area_id(client, "D")
    data(client.post("/api/simulation/outage", json={"scenario": "multi_meter_loss", "service_area_id": a}))
    assert active_incident(client, a) is None  # one bad reading is not enough

    client.post("/api/simulation/tick")
    inc = active_incident(client, a)
    assert inc["verification_status"] == "potential" and inc["scope"] == "area"

    advance(client, 10)  # verification period passes with evidence persisting
    inc = data(client.get(f"/api/incidents/{inc['id']}"))
    assert inc["verification_status"] == "confirmed" and inc["confirmation_method"] == "auto"
    alerts = [n for n in inc["notifications"] if n["kind"] == "outage_alert"]
    assert len(alerts) == 1 and alerts[0]["status"] in ("simulated_sent", "failed")
    job = data(client.get(f"/api/notifications/{alerts[0]['id']}"))
    eligible = [c for c in data(client.get(f"/api/customers?area_id={a}")) if c["whatsapp_eligible"]]
    assert len(job["messages"]) == len(eligible)
    assert "unexpected electricity interruption" in job["messages"][0]["body"]
    assert inc["estimated_customers"] >= inc["affected_meters"]

    data(client.post("/api/simulation/restore", json={"service_area_id": a}))
    client.post("/api/simulation/tick")
    inc = data(client.get(f"/api/incidents/{inc['id']}"))
    assert inc["resolution_status"] == "resolved" and inc["power_restored_at"]
    assert not [n for n in inc["notifications"] if n["kind"] == "restoration"]  # no automatic restoration message
    assert inc["restoration_suggested"] is True

    restored = data(client.post(f"/api/incidents/{inc['id']}/announce-restoration"))
    assert [n for n in restored["notifications"] if n["kind"] == "restoration"]
    assert client.post(f"/api/incidents/{inc['id']}/announce-restoration").status_code == 409


def test_comm_failure_is_not_an_outage(client):
    a = area_id(client, "E")
    data(client.post("/api/simulation/outage", json={"scenario": "comm_failure", "service_area_id": a}))
    advance(client, 40)
    meters = data(client.get(f"/api/meters?area_id={a}"))
    assert all(m["status"] == "offline" for m in meters)
    assert active_incident(client, a) is None
    assert any(e["type"] == "meter_offline" for e in data(client.get("/api/activity?limit=100")))


def test_manual_confirm_acknowledge_resolve_and_timeline(client):
    a = area_id(client, "A")
    r = client.put("/api/settings/detection", json={"auto_confirm": False})
    assert r.status_code == 200
    client.post("/api/simulation/outage", json={"scenario": "multi_meter_loss", "service_area_id": a})
    client.post("/api/simulation/tick")
    advance(client, 30)
    inc = active_incident(client, a)
    assert inc["verification_status"] == "potential"
    data(client.post(f"/api/incidents/{inc['id']}/acknowledge"))
    assert client.post(f"/api/incidents/{inc['id']}/acknowledge").status_code == 409
    data(client.post(f"/api/incidents/{inc['id']}/investigate", json={"note": "Crew dispatched"}))
    confirmed = data(client.post(f"/api/incidents/{inc['id']}/confirm", json={"notify_customers": True}))
    assert confirmed["confirmation_method"] == "manual"
    upd = data(client.post(f"/api/incidents/{inc['id']}/send-update", json={"eta": "6:00 PM today"}))
    assert any(n["kind"] == "outage_update" for n in upd["notifications"])
    resolved = data(client.post(f"/api/incidents/{inc['id']}/resolve", json={"note": "Fuse replaced"}))
    types = [e["type"] for e in resolved["events"]]
    assert types[0] == "detected" and "acknowledged" in types and "confirmed" in types and types[-1] == "resolved"
    assert client.post(f"/api/incidents/{inc['id']}/resolve").status_code == 409


def test_reject_does_not_retrigger_until_restored(client):
    a = area_id(client, "B")
    client.put("/api/settings/detection", json={"auto_confirm": False})
    client.post("/api/simulation/outage", json={"scenario": "multi_meter_loss", "service_area_id": a})
    client.post("/api/simulation/tick")
    inc = active_incident(client, a)
    data(client.post(f"/api/incidents/{inc['id']}/reject", json={"reason": "Field test"}))
    for _ in range(3):
        client.post("/api/simulation/tick")
    assert active_incident(client, a) is None
    assert client.post(f"/api/incidents/{inc['id']}/confirm").status_code == 409
