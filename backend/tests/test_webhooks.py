"""WhatsApp webhook: verification handshake, signature check, idempotent status updates, opt-out replies."""
import hashlib
import hmac
import json

from sqlalchemy import select

from app.models import Customer, NotificationMessage

from .conftest import data
from .test_delivery import LIVE, FakeCloud, add_mpm_customer, send_announcement, with_fake

SECRET = "app-secret-for-tests"


def signed(client, payload, secret=SECRET):
    raw = json.dumps(payload).encode()
    sig = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return client.post("/api/webhooks/whatsapp", content=raw,
                       headers={"Content-Type": "application/json", "X-Hub-Signature-256": sig})


def status_payload(wamid, status, ts=1760000000, errors=None):
    st = {"id": wamid, "status": status, "timestamp": str(ts), "recipient_id": "250788555001"}
    if errors:
        st["errors"] = errors
    return {"object": "whatsapp_business_account", "entry": [{"id": "WABA", "changes": [
        {"field": "messages", "value": {"messaging_product": "whatsapp", "statuses": [st]}}]}]}


def live_client(make_client):
    fake = FakeCloud()
    client = make_client(with_fake(fake), **{**LIVE, "meta_app_secret": SECRET, "whatsapp_verify_token": "verify-me"})
    cid = add_mpm_customer(client)
    job = send_announcement(client)
    msg = next(m for m in job["messages"] if m["customer_id"] == cid)
    return client, job, msg


def test_verification_handshake(make_client):
    client = make_client(whatsapp_verify_token="verify-me")
    ok = client.get("/api/webhooks/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "verify-me",
                                                      "hub.challenge": "1158201444"})
    assert ok.status_code == 200 and ok.text == "1158201444"
    bad = client.get("/api/webhooks/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "nope",
                                                       "hub.challenge": "1"})
    assert bad.status_code == 403
    assert make_client().get("/api/webhooks/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "",
                                                               "hub.challenge": "1"}).status_code == 403


def test_signature_required(make_client):
    client, _, msg = live_client(make_client)
    payload = status_payload(msg["provider_message_id"], "delivered")
    assert client.post("/api/webhooks/whatsapp", json=payload).status_code == 401
    assert signed(client, payload, secret="wrong").status_code == 401
    assert signed(client, payload).status_code == 200


def test_cloud_mode_without_app_secret_rejects_webhooks(make_client):
    client = make_client(**LIVE)
    assert client.post("/api/webhooks/whatsapp", json=status_payload("x", "sent")).status_code == 503


def test_statuses_are_monotonic_and_idempotent(make_client):
    client, job, msg = live_client(make_client)
    wamid = msg["provider_message_id"]
    assert data(signed(client, status_payload(wamid, "delivered")))["status_updates"] == 1
    assert data(signed(client, status_payload(wamid, "delivered")))["duplicates"] == 1
    assert data(signed(client, status_payload(wamid, "read", ts=1760000100)))["status_updates"] == 1
    # A late "sent" or "delivered" never moves the status backwards.
    assert data(signed(client, status_payload(wamid, "sent")))["status_updates"] == 0
    after = next(m for m in data(client.get(f"/api/notifications/{job['id']}"))["messages"] if m["id"] == msg["id"])
    assert after["status"] == "read" and after["delivered_at"] and after["read_at"]
    assert data(signed(client, status_payload("wamid.unknown", "delivered")))["unknown_messages"] == 1


def test_failed_status_records_error(make_client):
    client, job, msg = live_client(make_client)
    errors = [{"code": 131026, "title": "Message undeliverable", "error_data": {"details": "Recipient unavailable"}}]
    data(signed(client, status_payload(msg["provider_message_id"], "failed", errors=errors)))
    after = next(m for m in data(client.get(f"/api/notifications/{job['id']}"))["messages"] if m["id"] == msg["id"])
    assert after["status"] == "failed" and after["error_code"] == "131026" and "unavailable" in after["error"]
    assert data(client.get(f"/api/notifications/{job['id']}"))["failed_count"] >= 1


def test_stop_reply_opts_out_and_start_opts_in(make_client):
    client, _, _ = live_client(make_client)

    def reply(text, mid):
        return {"entry": [{"changes": [{"value": {"messages": [
            {"from": "250788555001", "id": mid, "type": "text", "text": {"body": text}}]}}]}]}

    assert data(signed(client, reply("stop", "wamid.in1")))["opt_outs"] == 1
    db = client.app.state.db.SessionLocal()
    customer = db.scalar(select(Customer).where(Customer.phone == "+250788555001"))
    assert customer.whatsapp_opt_in is False and customer.consent_source == "whatsapp_reply"
    db.close()
    assert data(signed(client, reply("stop", "wamid.in1")))["duplicates"] == 1
    assert data(signed(client, reply("START", "wamid.in2")))["opt_ins"] == 1
    assert data(signed(client, reply("hello", "wamid.in3")))["opt_ins"] == 0


def test_opted_out_customer_is_no_longer_targeted(make_client):
    client, _, _ = live_client(make_client)
    signed(client, {"entry": [{"changes": [{"value": {"messages": [
        {"from": "250788555001", "id": "wamid.in9", "type": "text", "text": {"body": "STOP"}}]}}]}]})
    job = send_announcement(client)
    db = client.app.state.db.SessionLocal()
    cid = db.scalar(select(Customer.id).where(Customer.phone == "+250788555001"))
    assert db.scalar(select(NotificationMessage).where(NotificationMessage.job_id == job["id"],
                                                       NotificationMessage.customer_id == cid)) is None
    db.close()
