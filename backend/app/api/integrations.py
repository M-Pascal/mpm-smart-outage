"""Integration endpoints: MPM, WhatsApp Cloud API webhook, and meter telemetry ingestion."""
from __future__ import annotations

import hmac
import json
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from ..channels.router import get_router
from ..clock import now as clock_now
from ..clock import to_naive_utc
from ..db import WRITE_LOCK
from ..errors import AppError, ok
from ..integrations import mpm
from ..integrations.mpm import MpmClient, MpmError
from ..services import monitoring, mpm_sync, webhooks
from .deps import get_db

router = APIRouter(prefix="/api")
log = logging.getLogger("powerchat.api.integrations")


@router.get("/integrations")
def integrations(request: Request):
    config = request.app.state.config
    return ok({"whatsapp": get_router().status(), "mpm": mpm.status(config),
               "webhook_path": "/api/webhooks/whatsapp", "telemetry_enabled": bool(config.telemetry_api_key)})


@router.post("/integrations/mpm/test")
def test_mpm(request: Request):
    config = request.app.state.config
    if not config.mpm_configured:
        return ok({"ok": False, "message": "MPM is not configured (MPM_BASE_URL, MPM_EMAIL, MPM_PASSWORD)."})
    return ok(MpmClient(config).test_connection())


@router.post("/integrations/mpm/sync")
def sync_mpm(request: Request, db: Session = Depends(get_db)):
    config = request.app.state.config
    if not config.mpm_configured:
        raise AppError(409, "not_configured", "MPM is not configured (MPM_BASE_URL, MPM_EMAIL, MPM_PASSWORD).")
    try:
        summary = mpm_sync.sync(db, MpmClient(config))
    except MpmError as exc:
        raise AppError(502, "mpm_error", str(exc))
    return ok(summary)


# --------------------------------------------------------------- WhatsApp
@router.get("/webhooks/whatsapp", response_class=PlainTextResponse)
def whatsapp_verify(request: Request, mode: str = Query("", alias="hub.mode"),
                    token: str = Query("", alias="hub.verify_token"), challenge: str = Query("", alias="hub.challenge")):
    """Meta's subscription handshake: echo hub.challenge when hub.verify_token matches WHATSAPP_VERIFY_TOKEN."""
    expected = request.app.state.config.whatsapp_verify_token
    if mode == "subscribe" and expected and hmac.compare_digest(token, expected):
        return challenge
    raise AppError(403, "forbidden", "Webhook verification failed")


@router.post("/webhooks/whatsapp")
async def whatsapp_events(request: Request, x_hub_signature_256: Optional[str] = Header(None),
                          db: Session = Depends(get_db)):
    config = request.app.state.config
    raw = await request.body()
    if config.meta_app_secret:
        if not webhooks.valid_signature(config.meta_app_secret, raw, x_hub_signature_256):
            log.warning("rejected WhatsApp webhook with missing or invalid signature")
            raise AppError(401, "invalid_signature", "Invalid X-Hub-Signature-256")
    elif config.whatsapp_mode != "mock":
        # Without the app secret, authenticity cannot be checked; never trust unsigned callbacks in cloud mode.
        raise AppError(503, "not_configured", "META_APP_SECRET is required to accept WhatsApp webhooks")
    try:
        payload = json.loads(raw or b"{}")
    except ValueError:
        raise AppError(400, "invalid_json", "Body is not valid JSON")
    return ok(webhooks.process(db, payload))


# --------------------------------------------------------------- telemetry
class ReadingIn(BaseModel):
    meter_serial: str = Field(min_length=1, max_length=40)
    voltage: float = Field(ge=0, le=1000)
    current: Optional[float] = Field(None, ge=0)
    power_kw: Optional[float] = Field(None, ge=0)
    timestamp: Optional[datetime] = None

    @field_validator("timestamp", mode="after")
    @classmethod
    def _utc(cls, v: Optional[datetime]) -> Optional[datetime]:
        return to_naive_utc(v) if v else v


class ReadingsIn(BaseModel):
    readings: list[ReadingIn] = Field(min_length=1, max_length=5000)


@router.post("/telemetry/readings")
def ingest(body: ReadingsIn, request: Request, x_powerchat_key: Optional[str] = Header(None),
           db: Session = Depends(get_db)):
    """Meter readings for MPM-synced meters (e.g. pushed by an MPM plugin or a meter-vendor integration)."""
    expected = request.app.state.config.telemetry_api_key
    if not expected:
        raise AppError(503, "not_configured", "Telemetry ingestion is disabled (TELEMETRY_API_KEY not set)")
    if not x_powerchat_key or not hmac.compare_digest(x_powerchat_key, expected):
        raise AppError(401, "unauthorized", "Invalid or missing X-PowerChat-Key header")
    t = clock_now()
    with WRITE_LOCK:
        result = monitoring.ingest_readings(db, [r.model_dump() for r in body.readings], t)
        monitoring.incidents_tick(db, t)
        db.commit()
    return ok(result)
