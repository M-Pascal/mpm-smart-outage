"""Response format, customers, templates, notification center, channels, settings, analytics."""
from .conftest import area_id, data


def test_envelope_and_error_format(client):
    assert "data" in client.get("/api/health").json()
    r = client.get("/api/incidents/99999")
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"
    r = client.post("/api/customers", json={"name": "X"})
    err = r.json()["error"]
    assert r.status_code == 422 and err["code"] == "validation_error" and err["details"]


def test_customer_crud_and_validation(client):
    a = area_id(client, "A")
    bad = client.post("/api/customers", json={"name": "Test User", "phone": "0788", "service_area_id": a})
    assert bad.status_code == 422 and bad.json()["error"]["details"][0]["field"] == "phone"
    c = data(client.post("/api/customers", json={"name": "Test User", "phone": "+250700999001", "service_area_id": a,
                                                  "whatsapp_opt_in": True, "create_meter": True}), 201)
    assert c["meter_serial"] and c["whatsapp_eligible"]
    dup = client.post("/api/customers", json={"name": "Other", "phone": "+250700999001", "service_area_id": a})
    assert dup.status_code == 422
    upd = data(client.patch(f"/api/customers/{c['id']}", json={"whatsapp_opt_in": False}))
    assert upd["whatsapp_eligible"] is False and upd["ineligible_reason"] == "no WhatsApp consent"
    found = data(client.get("/api/customers?q=Test User"))
    assert [x["id"] for x in found] == [c["id"]]
    assert data(client.get(f"/api/customers/{c['id']}"))["recent_messages"] == []


def test_manual_notification_draft_schedule_send_cancel(client):
    a = area_id(client, "C")
    preview = data(client.post("/api/notifications/preview", json={
        "template_key": "general_announcement", "area_ids": [a], "context": {"message": "Office closed Friday."}}))
    assert "Office closed Friday." in preview["body"] and preview["recipients"]["eligible"] > 0
    draft = data(client.post("/api/notifications", json={"template_key": "general_announcement", "area_ids": [a],
                                                          "context": {"message": "Hello"}, "mode": "draft"}), 201)
    assert draft["status"] == "draft"
    sent = data(client.post("/api/notifications/simulate", json={"job_id": draft["id"]}))
    assert sent["status"] in ("simulated_sent", "failed") and sent["simulated"]
    past = client.post("/api/notifications", json={"template_key": "general_announcement", "area_ids": [a],
                                                    "mode": "schedule", "send_at": "2020-01-01T00:00:00Z"})
    assert past.status_code == 422
    future = data(client.post("/api/notifications", json={"template_key": "general_announcement", "area_ids": [a],
                                                           "context": {"message": "x"}, "mode": "schedule",
                                                           "send_at": "2099-01-01T00:00:00Z"}), 201)
    assert data(client.post(f"/api/notifications/{future['id']}/cancel"))["status"] == "cancelled"
    assert client.post(f"/api/notifications/{future['id']}/cancel").status_code == 409


def test_retry_failed_messages(client):
    client.put("/api/settings/notifications", json={"simulated_failure_rate": 0.5})
    ids = [area_id(client, c) for c in "ABCDE"]
    job = data(client.post("/api/notifications", json={"template_key": "general_announcement", "area_ids": ids,
                                                        "context": {"message": "Test"}, "mode": "send_now"}), 201)
    job = data(client.get(f"/api/notifications/{job['id']}"))
    assert job["failed_count"] > 0
    client.put("/api/settings/notifications", json={"simulated_failure_rate": 0.0})
    retried = data(client.post(f"/api/notifications/{job['id']}/retry"))
    assert retried["failed_count"] == 0 and retried["status"] == "simulated_sent"
    assert client.post(f"/api/notifications/{job['id']}/retry").status_code == 409


def test_template_edit_validation_and_reset(client):
    bad = client.put("/api/templates/power_restored", json={"body": "Power is back in {area} {nonsense}"})
    assert bad.status_code == 422 and "nonsense" in bad.json()["error"]["message"]
    ok = data(client.put("/api/templates/power_restored", json={"body": "Power is back in {area}. Thanks!"}))
    assert ok["body"].startswith("Power is back")
    reset = data(client.post("/api/templates/power_restored/reset"))
    assert "has been restored" in reset["body"]


def test_channel_announcement_has_no_private_data(client):
    outage = data(client.get("/api/outages/scheduled?status=notification_queued"))[0]
    text = data(client.post("/api/channels/announcement", json={"scheduled_outage_id": outage["id"]}))["text"]
    assert outage["service_areas"][0]["name"] in text and "+250" not in text and "Dear" not in text
    r = client.post("/api/channels/announcement", json={"custom_text": "Call +250 700 100 001 for help"})
    assert r.status_code == 422


def test_settings_validation(client):
    r = client.put("/api/settings/detection", json={"restore_voltage_min": 40, "outage_voltage_max": 50})
    assert r.status_code == 422
    r = client.put("/api/settings/general", json={"timezone": "Mars/Base"})
    assert r.status_code == 422
    env = data(client.get("/api/settings"))["environment"]
    assert env["whatsapp"]["connected"] is False and env["mpm"]["connected"] is False
    assert data(client.post("/api/integrations/mpm/test"))["ok"] is False


def test_dashboard_and_analytics_use_shared_data(client):
    dash = data(client.get("/api/dashboard"))
    s = dash["summary"]
    assert s["total_meters"] == sum(a["meter_count"] for a in dash["areas"])
    assert s["notifications_scheduled"] == len(data(client.get("/api/notifications?status=scheduled")))
    stats = data(client.get("/api/analytics"))
    assert stats["simulated"] is True and stats["kpis"]["unexpected_outages"] >= 10
    assert 0 <= stats["kpis"]["failure_rate"] < 0.5
    series = data(client.get("/api/monitoring/series?range=24h"))
    assert len(series) > 50 and all("power_kw" in p for p in series)


def test_search(client):
    results = data(client.get("/api/search?q=Market"))
    assert any(r["type"] == "service_area" for r in results)
    assert any(r["type"] == "customer" for r in results)
