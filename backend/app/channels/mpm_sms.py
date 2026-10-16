"""SMS channel that reuses MicroPowerManager's own SMS pipeline.

PowerChat does not talk to SMS gateways itself: it calls MPM's POST /api/sms/storeandsend, so MPM's configured
gateway (Africa's Talking, TextBee, Viber), its sms table and its resend command keep doing the work.
"""
from __future__ import annotations

from ..integrations.mpm import MpmClient, MpmError
from .base import OutboundMessage, SendResult


class MpmSmsChannel:
    provider = "mpm_sms"
    channel = "sms"
    simulated = False

    def __init__(self, client: MpmClient) -> None:
        self._client = client

    def send(self, message: OutboundMessage) -> SendResult:
        try:
            sms = self._client.send_sms(message.to, message.body)
        except MpmError as exc:
            if exc.status is None and not exc.retryable:
                return SendResult("unknown", error_code="outcome_unknown", error_message=str(exc)[:300])
            return SendResult("retryable_error" if exc.retryable else "permanent_error", http_status=exc.status,
                              error_code=f"mpm_{exc.status or 'network'}", error_message=str(exc)[:300])
        sms_id = sms.get("id") or sms.get("uuid")
        return SendResult("accepted", provider_message_id=f"mpm-sms-{sms_id}" if sms_id else None)
