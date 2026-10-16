"""WhatsApp Business Cloud API channel (Meta Graph API, template messages).

POST https://graph.facebook.com/{version}/{phone-number-id}/messages
Business-initiated messages outside the 24-hour customer-service window must use pre-approved templates,
so every notification is sent as a template with positional body parameters.

Duplicate safety: the Cloud API has no idempotency key. A request that may have reached Meta (read timeout,
dropped connection after sending) is reported as outcome "unknown" and is never retried automatically; only
errors that prove the message was not accepted are retryable.
"""
from __future__ import annotations

import logging

import httpx

from ..config import Config
from ..phone import mask
from .base import OutboundMessage, SendResult

log = logging.getLogger("powerchat.whatsapp")

GRAPH_URL = "https://graph.facebook.com"
# Codes Meta documents as "try again later" (rate limits, temporary unavailability, unknown send error).
RETRYABLE_CODES = {"4", "80007", "130429", "131000", "131016", "131056", "133004"}
# Everything else (undeliverable recipient, template missing or parameter mismatch, expired token, quality
# restrictions such as 131048) needs an operator to fix something, so it is a permanent failure.


class WhatsAppCloudChannel:
    provider = "whatsapp_cloud"
    channel = "whatsapp"
    simulated = False

    def __init__(self, config: Config, client: httpx.Client | None = None) -> None:
        if not config.whatsapp_cloud_configured:
            raise RuntimeError("WhatsApp Cloud API credentials are not configured")
        self._config = config
        self._client = client or httpx.Client(timeout=httpx.Timeout(10.0, connect=5.0))

    @property
    def url(self) -> str:
        c = self._config
        return f"{GRAPH_URL}/{c.whatsapp_api_version}/{c.whatsapp_phone_number_id}/messages"

    @staticmethod
    def build_payload(message: OutboundMessage) -> dict:
        payload: dict = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": message.to.lstrip("+"),
            "type": "template",
            "template": {"name": message.template, "language": {"code": message.language}},
        }
        if message.parameters:
            payload["template"]["components"] = [
                {"type": "body", "parameters": [{"type": "text", "text": p} for p in message.parameters]}
            ]
        return payload

    def send(self, message: OutboundMessage) -> SendResult:
        try:
            response = self._client.post(
                self.url,
                json=self.build_payload(message),
                headers={"Authorization": f"Bearer {self._config.whatsapp_access_token}"},
            )
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            # The request never reached Meta.
            log.warning("whatsapp send not delivered to provider ref=%s to=%s: %s", message.reference,
                        mask(message.to), type(exc).__name__)
            return SendResult("retryable_error", error_code="network", error_message="Could not connect to WhatsApp API")
        except httpx.HTTPError as exc:
            log.error("whatsapp send outcome unknown ref=%s to=%s: %s", message.reference, mask(message.to),
                      type(exc).__name__)
            return SendResult("unknown", error_code="outcome_unknown",
                              error_message="The request may have reached WhatsApp; not retried automatically")
        return self._parse(response, message)

    def _parse(self, response: httpx.Response, message: OutboundMessage) -> SendResult:
        try:
            body = response.json()
        except ValueError:
            body = {}
        if response.status_code < 300:
            messages = body.get("messages") or []
            wamid = messages[0].get("id") if messages else None
            if not wamid:
                return SendResult("unknown", http_status=response.status_code, error_code="no_message_id",
                                  error_message="WhatsApp accepted the request but returned no message id")
            log.info("whatsapp accepted ref=%s to=%s wamid=%s", message.reference, mask(message.to), wamid)
            return SendResult("accepted", provider_message_id=wamid, http_status=response.status_code)

        error = body.get("error") or {}
        code = str(error.get("code", response.status_code))
        detail = (error.get("error_data") or {}).get("details") or error.get("message") or response.reason_phrase
        retry_after = response.headers.get("Retry-After")
        retryable = response.status_code == 429 or response.status_code >= 500 or code in RETRYABLE_CODES
        log.warning("whatsapp rejected ref=%s to=%s http=%s code=%s retryable=%s", message.reference,
                    mask(message.to), response.status_code, code, retryable)
        return SendResult(
            "retryable_error" if retryable else "permanent_error",
            http_status=response.status_code,
            error_code=code,
            error_message=str(detail)[:300],
            retry_after_seconds=float(retry_after) if retry_after and retry_after.isdigit() else None,
        )
