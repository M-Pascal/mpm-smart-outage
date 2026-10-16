"""MicroPowerManager client, sync, SMS reuse and telemetry. Response shapes follow MPM's controllers
(ApiResource-wrapped Laravel paginators and JWT login); no real MPM instance is contacted."""
import json

import httpx
import pytest
from sqlalchemy import select

from app.channels.base import OutboundMessage
from app.channels.mpm_sms import MpmSmsChannel
from app.channels.router import ChannelRouter
from app.config import Config
from app.integrations.mpm import MpmClient, _unwrap_page
from app.models import Customer, Meter, ServiceArea
from app.services import mpm_sync

from .conftest import data

CONFIG = Config(mpm_base_url="https://mpm.example.org", mpm_email="powerchat@example.org", mpm_password="pw",
                mpm_default_country_code="250", mpm_sms_enabled=True)


def page(items, current=1, last=1):
    # GET /api/people returns ApiResource::make($paginator) -> {"data": {"current_page": n, "data": [...], ...}}
    return {"data": {"current_page": current, "data": items, "last_page": last, "per_page": 100, "total": len(items)}}


PEOPLE_PAGE_1 = [
    {"id": 11, "name": "Aline", "surname": "Uwase", "is_customer": 1,
     "addresses": [{"phone": "0788 400 011", "is_primary": 1, "city_id": 5}],
     "devices": [{"device_serial": "MPM-METER-11", "device_type": "meter"}]},
    {"id": 12, "name": "Jean", "surname": "Bosco", "is_customer": 1,
     "addresses": [{"phone": "+250788400012", "is_primary": 1, "city_id": 6}], "devices": []},
]
PEOPLE_PAGE_2 = [
    {"id": 13, "name": "No", "surname": "Phone", "is_customer": 1, "addresses": [{"phone": None, "is_primary": 1, "city_id": 5}]},
    {"id": 14, "name": "Elsewhere", "surname": "", "is_customer": 1,
     "addresses": [{"phone": "+250788400014", "is_primary": 1, "city_id": 99}]},
]


class FakeMpm:
    def __init__(self):
        self.requests, self.logins, self.expire_next = [], 0, False
        self.people = [PEOPLE_PAGE_1, PEOPLE_PAGE_2]

    def __call__(self, request: httpx.Request):
        self.requests.append((request.method, request.url.path, dict(request.url.params)))
        path = request.url.path
        if path == "/api/auth/login":
            body = json.loads(request.read())
            if body != {"email": "powerchat@example.org", "password": "pw"}:
                return httpx.Response(401, json={"message": "Unauthenticated."})
            self.logins += 1
            return httpx.Response(200, json={"access_token": f"jwt-{self.logins}", "token_type": "bearer",
                                             "expires_in": 3600, "user": {}, "roles": [], "permissions": []})
        if request.headers.get("authorization") != f"Bearer jwt-{self.logins}" or self.expire_next:
            self.expire_next = False
            return httpx.Response(401, json={"message": "Token expired"})
        if path == "/api/mini-grids":
            return httpx.Response(200, json=page([{"id": 1, "name": "Lake Kivu MG", "cluster_id": 1}]))
        if path == "/api/cities":
            return httpx.Response(200, json=page([{"id": 5, "name": "Gisenyi", "mini_grid_id": 1},
                                                  {"id": 6, "name": "Nyamyumba", "mini_grid_id": 1},
                                                  {"id": 7, "name": "Orphan city", "mini_grid_id": 42}]))
        if path == "/api/people":
            n = int(request.url.params.get("page", 1))
            assert request.url.params.get("is_customer") == "1"
            return httpx.Response(200, json=page(self.people[n - 1], current=n, last=len(self.people)))
        if path == "/api/sms/storeandsend":
            body = json.loads(request.read())
            return httpx.Response(200, json={"data": {"id": 777, "receiver": body["phone"], "body": body["message"]}})
        return httpx.Response(404, json={"message": "Not found"})


def mpm_client(fake=None):
    fake = fake or FakeMpm()
    return MpmClient(CONFIG, client=httpx.Client(transport=httpx.MockTransport(fake))), fake


def test_unwrap_page_shapes():
    assert _unwrap_page(page([{"id": 1}], last=3)) == ([{"id": 1}], 3)
    assert _unwrap_page({"data": [{"id": 1}], "meta": {"last_page": 2}}) == ([{"id": 1}], 2)
    assert _unwrap_page([{"id": 1}]) == ([{"id": 1}], 1)


def test_login_pagination_and_token_refresh():
    client, fake = mpm_client()
    people = list(client.customers())
    assert [p["id"] for p in people] == [11, 12, 13, 14] and fake.logins == 1
    fake.expire_next = True  # MPM rejects the token once: the client logs in again and repeats the request
    assert client.mini_grids()[0]["name"] == "Lake Kivu MG" and fake.logins == 2


def test_bad_credentials_raise_clear_error():
    cfg = Config(mpm_base_url="https://mpm.example.org", mpm_email="x", mpm_password="wrong")
    client = MpmClient(cfg, client=httpx.Client(transport=httpx.MockTransport(FakeMpm())))
    assert client.test_connection() == {"ok": False, "message": "MPM rejected the service-account credentials"}


def test_sync_maps_mpm_entities_and_preserves_consent(client):
    db = client.app.state.db.SessionLocal()
    mpm, _ = mpm_client()
    summary = mpm_sync.sync(db, mpm)
    assert summary["mini_grids"] == 1 and summary["service_areas"] == 2 and summary["customers_created"] == 2
    assert summary["skipped"] == {"city without a synced mini-grid": 1, "missing or invalid phone number": 1,
                                  "no primary address in a synced city": 1}
    aline = db.scalar(select(Customer).where(Customer.mpm_person_id == 11))
    assert aline.phone == "+250788400011" and aline.source == "mpm" and aline.whatsapp_opt_in is False
    assert db.scalar(select(ServiceArea).where(ServiceArea.mpm_city_id == 5)).name == "Gisenyi"
    meter = db.scalar(select(Meter).where(Meter.serial == "MPM-METER-11"))
    assert meter.source == "mpm" and meter.customer_id == aline.id

    aline.whatsapp_opt_in, aline.consent_source = True, "operator"  # consent recorded in PowerChat
    db.commit()
    mpm2, fake2 = mpm_client()
    fake2.people = [PEOPLE_PAGE_1[:1]]  # Jean was removed from MPM
    summary = mpm_sync.sync(db, mpm2)
    db.refresh(aline)
    assert aline.whatsapp_opt_in is True and summary["customers_updated"] == 1 and summary["customers_deactivated"] == 1
    assert db.scalar(select(Customer).where(Customer.mpm_person_id == 12)).account_status == "inactive"
    db.close()


def test_sync_endpoint_requires_configuration(client):
    r = client.post("/api/integrations/mpm/sync")
    assert r.status_code == 409 and r.json()["error"]["code"] == "not_configured"


def test_sms_goes_through_mpm_storeandsend():
    mpm, fake = mpm_client()
    result = MpmSmsChannel(mpm).send(OutboundMessage("+250788400011", "t", "en", [], "Power cut at 9 AM", "1-2"))
    assert result.outcome == "accepted" and result.provider_message_id == "mpm-sms-777"
    method, path, _ = fake.requests[-1]
    assert (method, path) == ("POST", "/api/sms/storeandsend")


def test_sms_customers_routed_to_mpm_when_enabled():
    router = ChannelRouter(CONFIG, mpm_sms=MpmSmsChannel(mpm_client()[0]))
    mpm_customer = Customer(name="x", phone="+250788400011", source="mpm", notification_preference="sms",
                            account_status="active", whatsapp_opt_in=False)
    demo_customer = Customer(name="y", phone="+250788400012", source="demo", notification_preference="sms",
                             account_status="active", whatsapp_opt_in=False)
    assert router.route(mpm_customer).channel.provider == "mpm_sms"
    assert router.route(demo_customer).channel.provider == "mock"


@pytest.fixture
def telemetry_client(make_client):
    client = make_client(telemetry_api_key="ingest-key")
    db = client.app.state.db.SessionLocal()
    area = db.scalar(select(ServiceArea).where(ServiceArea.code == "B"))
    for i in range(3):
        db.add(Meter(serial=f"MPM-T{i}", source="mpm", service_area_id=area.id, status="normal"))
    db.commit()
    db.close()
    return client


def test_telemetry_requires_key(telemetry_client, make_client):
    body = {"readings": [{"meter_serial": "MPM-T0", "voltage": 0}]}
    assert telemetry_client.post("/api/telemetry/readings", json=body).status_code == 401
    assert make_client().post("/api/telemetry/readings", json=body).status_code == 503


def test_telemetry_detects_repeated_near_zero_voltage(telemetry_client):
    headers = {"X-PowerChat-Key": "ingest-key"}
    readings = {"readings": [{"meter_serial": f"MPM-T{i}", "voltage": 1.5} for i in range(3)]
                + [{"meter_serial": "PP-B009", "voltage": 0}, {"meter_serial": "unknown", "voltage": 0}]}
    first = data(telemetry_client.post("/api/telemetry/readings", json=readings, headers=headers))
    assert first["accepted"] == 3 and set(first["unknown_meter_serials"]) == {"PP-B009", "unknown"}  # demo meter refused
    assert first["status_changes"] == 0  # a single near-zero reading is not enough
    second = data(telemetry_client.post("/api/telemetry/readings", json=readings, headers=headers))
    assert second["status_changes"] == 3
    incidents = data(telemetry_client.get("/api/incidents?status=active"))
    assert incidents and incidents[0]["verification_status"] == "potential" and incidents[0]["evidence_type"] == "voltage"


def test_mpm_owned_fields_are_read_only(make_client):
    from .test_delivery import add_mpm_customer
    client = make_client()
    cid = add_mpm_customer(client, opt_in=False)
    r = client.patch(f"/api/customers/{cid}", json={"phone": "+250788999999"})
    assert r.status_code == 409 and "MicroPowerManager" in r.json()["error"]["message"]
    updated = data(client.patch(f"/api/customers/{cid}", json={"whatsapp_opt_in": True}))
    assert updated["whatsapp_opt_in"] is True and updated["consent_source"] == "operator"
