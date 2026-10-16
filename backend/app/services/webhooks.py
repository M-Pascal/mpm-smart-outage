"""WhatsApp Cloud API webhook processing: delivery statuses and customer opt-out/opt-in replies.

Authenticity: Meta signs every POST with HMAC-SHA256 of the raw body using the app secret
(header X-Hub-Signature-256: "sha256=<hex>"). Unsigned or wrongly signed requests are rejected.
Idempotency: each status/message is recorded once in webhook_events (UNIQUE event_key), so Meta's
at-least-once redelivery never applies an update twice.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..clock import now as clock_now
from ..db import WRITE_LOCK
from ..models import Customer, NotificationMessage, WebhookEvent
from ..phone import mask
from . import activity
from .notifications import apply_status_update

log = logging.getLogger("powerchat.webhooks")

OPT_OUT_KEYWORDS = {"STOP", "STOP ALL", "UNSUBSCRIBE", "OPT OUT", "OPTOUT", "HAGARIKA"}
OPT_IN_KEYWORDS = {"START", "SUBSCRIBE", "OPT IN", "OPTIN"}


def valid_signature(app_secret: str, raw_body: bytes, header: str | None) -> bool:
    if not app_secret or not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header.removeprefix("sha256="))


def _record(db: Session, key: str, event_type: str, summary: str) -> bool:
    """True if this event is new. Uses a savepoint so a duplicate does not abort the surrounding work."""
    try:
        with db.begin_nested():
            db.add(WebhookEvent(provider="whatsapp_cloud", event_key=key, event_type=event_type, summary=summary[:300],
                                received_at=clock_now()))
        return True
    except IntegrityError:
        return False


def _ts(value: Any) -> datetime:
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc).replace(tzinfo=None)
    except (TypeError, ValueError):
        return clock_now()


def process(db: Session, payload: dict[str, Any]) -> dict[str, int]:
    counts = {"statuses": 0, "status_updates": 0, "duplicates": 0, "unknown_messages": 0, "opt_outs": 0, "opt_ins": 0}
    with WRITE_LOCK:
        for entry in payload.get("entry") or []:
            for change in entry.get("changes") or []:
                value = change.get("value") or {}
                for status in value.get("statuses") or []:
                    _status(db, status, counts)
                for message in value.get("messages") or []:
                    _inbound(db, message, counts)
        db.commit()
    return counts


def _status(db: Session, status: dict[str, Any], counts: dict[str, int]) -> None:
    counts["statuses"] += 1
    wamid, state = status.get("id"), status.get("status")
    if not wamid or not state:
        return
    if not _record(db, f"status:{wamid}:{state}", "status", f"{state} for {wamid}"):
        counts["duplicates"] += 1
        return
    message = db.scalar(select(NotificationMessage).where(NotificationMessage.provider_message_id == wamid))
    if message is None:
        counts["unknown_messages"] += 1
        return
    errors = status.get("errors") or [{}]
    error = errors[0]
    detail = (error.get("error_data") or {}).get("details") or error.get("message") or error.get("title") or ""
    if apply_status_update(db, message, state, _ts(status.get("timestamp")), str(error.get("code") or ""), str(detail)):
        counts["status_updates"] += 1
        log.info("webhook status %s for message %s", state, message.id)


def _inbound(db: Session, message: dict[str, Any], counts: dict[str, int]) -> None:
    text = ((message.get("text") or {}).get("body") or "").strip().upper()
    if message.get("type") == "button":
        text = ((message.get("button") or {}).get("text") or "").strip().upper()
    if text not in OPT_OUT_KEYWORDS and text not in OPT_IN_KEYWORDS:
        return  # PowerChat only acts on consent keywords; other replies stay in the operator's WhatsApp inbox
    if not _record(db, f"message:{message.get('id')}", "inbound_message", f"consent keyword {text}"):
        counts["duplicates"] += 1
        return
    phone = "+" + str(message.get("from", "")).lstrip("+")
    customer = db.scalar(select(Customer).where(Customer.phone == phone))
    if customer is None:
        log.warning("consent keyword from unknown number %s", mask(phone))
        return
    opted_in = text in OPT_IN_KEYWORDS
    if customer.whatsapp_opt_in == opted_in:
        return
    customer.whatsapp_opt_in = opted_in
    customer.consent_source = "whatsapp_reply"
    customer.consent_updated_at = clock_now()
    counts["opt_ins" if opted_in else "opt_outs"] += 1
    activity.log(db, "consent_changed", f"{customer.name} {'opted in to' if opted_in else 'opted out of'} WhatsApp "
                 f"notifications by replying {text}", severity="warning" if not opted_in else "info",
                 entity_type="customer", entity_id=customer.id)
