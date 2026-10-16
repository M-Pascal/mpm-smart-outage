"""Routing, consent, live-send safety, retries and duplicate protection (fake provider; nothing leaves the test)."""
from datetime import timedelta

from sqlalchemy import select

from app.channels.base import SendResult
from app.channels.router import ChannelRouter
from app.models import Customer, DeliveryAttempt, NotificationMessage
from app.services import notifications

from .conftest import advance, area_id, data

LIVE = dict(whatsapp_mode="cloud", whatsapp_live_send_enabled=True, whatsapp_access_token="t",
            whatsapp_phone_number_id="1", whatsapp_allowed_recipients=["+250788555001"])


class FakeCloud:
    provider, channel, simulated = "whatsapp_cloud", "whatsapp", False

    def __init__(self, outcomes=None):
        self.calls, self.outcomes = [], list(outcomes or [])

    def send(self, message):
        self.calls.append(message)
        if self.outcomes:
            return self.outcomes.pop(0)
        return SendResult("accepted", provider_message_id=f"wamid.{message.reference}.{message.attempt}")


def with_fake(fake):
    return lambda config: ChannelRouter(config, whatsapp_cloud=fake)


def add_mpm_customer(client, area_code="A", phone="+250788555001", opt_in=True, person_id=9001):
    db = client.app.state.db.SessionLocal()
    c = Customer(name=f"MPM Person {person_id}", phone=phone, service_area_id=area_id(client, area_code), source="mpm",
                 mpm_person_id=person_id, whatsapp_opt_in=opt_in, notification_preference="whatsapp")
    db.add(c)
    db.commit()
    cid = c.id
    db.close()
    return cid


def send_announcement(client, area_code="A"):
    job = data(client.post("/api/notifications", json={"template_key": "general_announcement",
                                                        "area_ids": [area_id(client, area_code)],
                                                        "context": {"message": "Test"}, "mode": "send_now"}), 201)
    return data(client.get(f"/api/notifications/{job['id']}"))


def test_mock_mode_never_calls_provider_and_labels_simulated(make_client):
    fake = FakeCloud()
    client = make_client(with_fake(fake))
    add_mpm_customer(client)
    job = send_announcement(client)
    assert fake.calls == [] and job["simulated"] is True
    assert all(m["simulated"] and m["provider"] == "mock" for m in job["messages"])


def test_live_mode_sends_only_to_consenting_allowlisted_mpm_customers(make_client):
    fake = FakeCloud()
    client = make_client(with_fake(fake), **LIVE)
    add_mpm_customer(client, phone="+250788555001", person_id=1)  # allow-listed
    add_mpm_customer(client, phone="+250788555002", person_id=2)  # not allow-listed
    add_mpm_customer(client, phone="+250788555003", person_id=3, opt_in=False)  # no consent
    job = send_announcement(client)
    assert [m.to for m in fake.calls] == ["+250788555001"]  # demo customers in the area are never sent live
    by_phone = {m["customer_name"]: m for m in job["messages"]}
    assert by_phone["MPM Person 1"]["status"] == "sent" and by_phone["MPM Person 1"]["provider_message_id"].startswith("wamid.")
    assert by_phone["MPM Person 2"]["status"] == "failed" and by_phone["MPM Person 2"]["error_code"] == "not_allowlisted"
    assert "MPM Person 3" not in by_phone
    assert all(m["simulated"] for name, m in by_phone.items() if not name.startswith("MPM"))
    assert job["simulated"] is False


def test_live_send_requires_explicit_enable(make_client):
    fake = FakeCloud()
    client = make_client(with_fake(fake), **{**LIVE, "whatsapp_live_send_enabled": False})
    add_mpm_customer(client)
    send_announcement(client)
    assert fake.calls == []


def test_retryable_error_backs_off_then_succeeds_without_duplicates(make_client):
    fake = FakeCloud([SendResult("retryable_error", http_status=429, error_code="130429", error_message="rate")])
    client = make_client(with_fake(fake), **{**LIVE, "whatsapp_allowlist_disabled": True})
    cid = add_mpm_customer(client)
    job = send_announcement(client)
    msg = next(m for m in job["messages"] if m["customer_id"] == cid)
    assert msg["status"] == "retry_scheduled" and msg["next_retry_at"] and msg["attempts"] == 1
    client.post("/api/simulation/tick")  # retry not yet due
    assert len(fake.calls) == 1
    advance(client, 31)
    job = data(client.get(f"/api/notifications/{job['id']}"))
    msg = next(m for m in job["messages"] if m["customer_id"] == cid)
    assert msg["status"] == "sent" and msg["attempts"] == 2 and len(fake.calls) == 2
    advance(client, 120)
    assert len(fake.calls) == 2  # a sent message is never sent again
    db = client.app.state.db.SessionLocal()
    attempts = db.scalars(select(DeliveryAttempt).where(DeliveryAttempt.message_id == msg["id"])).all()
    assert [a.outcome for a in attempts] == ["retryable_error", "accepted"]
    db.close()


def test_retries_stop_after_max_attempts(make_client):
    rate = SendResult("retryable_error", http_status=429, error_code="130429", error_message="rate")
    fake = FakeCloud([rate, rate, rate, rate])
    client = make_client(with_fake(fake), **{**LIVE, "whatsapp_allowlist_disabled": True})
    cid = add_mpm_customer(client)
    job = send_announcement(client)
    for _ in range(4):
        advance(client, 600)
    msg = next(m for m in data(client.get(f"/api/notifications/{job['id']}"))["messages"] if m["customer_id"] == cid)
    assert msg["status"] == "failed" and msg["attempts"] == notifications.MAX_ATTEMPTS
    assert len(fake.calls) == notifications.MAX_ATTEMPTS


def test_unknown_outcome_is_never_retried_automatically(make_client):
    fake = FakeCloud([SendResult("unknown", error_code="outcome_unknown", error_message="timeout")])
    client = make_client(with_fake(fake), **{**LIVE, "whatsapp_allowlist_disabled": True})
    cid = add_mpm_customer(client)
    job = send_announcement(client)
    advance(client, 3600)
    msg = next(m for m in data(client.get(f"/api/notifications/{job['id']}"))["messages"] if m["customer_id"] == cid)
    assert msg["status"] == "failed" and msg["error_code"] == "outcome_unknown" and len(fake.calls) == 1
    # An operator can still choose to retry it.
    data(client.post(f"/api/notifications/{job['id']}/retry"))
    assert len(fake.calls) == 2


def test_interrupted_send_is_marked_unknown_not_resent(make_client):
    fake = FakeCloud()
    client = make_client(with_fake(fake), **{**LIVE, "whatsapp_allowlist_disabled": True})
    cid = add_mpm_customer(client)
    job = send_announcement(client)
    db = client.app.state.db.SessionLocal()
    msg = db.scalar(select(NotificationMessage).where(NotificationMessage.job_id == job["id"],
                                                      NotificationMessage.customer_id == cid))
    msg.status, msg.provider_message_id = "sending", None  # simulate a crash between claim and provider response
    msg.updated_at = msg.updated_at - timedelta(minutes=10)
    db.commit()
    db.close()
    calls = len(fake.calls)
    client.post("/api/simulation/tick")
    after = next(m for m in data(client.get(f"/api/notifications/{job['id']}"))["messages"] if m["customer_id"] == cid)
    assert after["status"] == "failed" and after["error_code"] == "outcome_unknown" and len(fake.calls) == calls


def test_consent_withdrawn_before_retry_blocks_send(make_client):
    fake = FakeCloud([SendResult("retryable_error", http_status=503, error_code="503", error_message="down")])
    client = make_client(with_fake(fake), **{**LIVE, "whatsapp_allowlist_disabled": True})
    cid = add_mpm_customer(client)
    job = send_announcement(client)
    client.patch(f"/api/customers/{cid}", json={"whatsapp_opt_in": False})
    advance(client, 60)
    msg = next(m for m in data(client.get(f"/api/notifications/{job['id']}"))["messages"] if m["customer_id"] == cid)
    assert msg["status"] == "failed" and msg["error_code"] == "not_eligible" and len(fake.calls) == 1


def test_sms_preference_uses_sms_channel(client):
    db = client.app.state.db.SessionLocal()
    sms_customer = db.scalar(select(Customer).where(Customer.notification_preference == "sms",
                                                    Customer.account_status == "active"))
    code = sms_customer.service_area.code
    db.close()
    job = send_announcement(client, code)
    msg = next(m for m in job["messages"] if m["customer_id"] == sms_customer.id)
    assert msg["channel"] == "sms" and msg["provider"] == "mock"


def test_mock_receipts_progress_to_delivered(client):
    job = send_announcement(client)
    sent = [m for m in job["messages"] if m["status"] == "sent"]
    assert sent
    advance(client, 20)
    job = data(client.get(f"/api/notifications/{job['id']}"))
    assert all(m["status"] in ("delivered", "read") for m in job["messages"] if m["id"] in {s["id"] for s in sent})
    assert job["delivered_count"] >= len(sent)


def test_whatsapp_template_definition(client):
    tpl = data(client.get("/api/templates/maintenance_reminder/whatsapp"))
    assert "{{1}}" in tpl["body"] and "{organization}" not in tpl["body"]
    assert [p["name"] for p in tpl["parameters"]][:2] == ["organization", "area"]
