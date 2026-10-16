"""Mock channel for demonstrations and tests. Never contacts any external service."""
from __future__ import annotations

import hashlib

from .base import OutboundMessage, SendResult

_PERMANENT = [
    ("131026", "Simulated: message undeliverable (number not on WhatsApp)"),
    ("131051", "Simulated: unsupported message type for recipient"),
]
_RETRYABLE = ("130429", "Simulated: provider rate limit reached")


class MockChannel:
    provider = "mock"
    simulated = True

    def __init__(self, channel: str = "whatsapp", failure_rate: float = 0.0) -> None:
        self.channel = channel
        self.failure_rate = failure_rate

    def send(self, message: OutboundMessage) -> SendResult:
        """Deterministic per (message, attempt): the same demo replays identically and retries can succeed."""
        h = int(hashlib.sha1(f"{message.reference}:{message.attempt}".encode()).hexdigest(), 16)
        if (h % 1000) < self.failure_rate * 1000:
            # One in three simulated failures is a transient rate limit, so retries are exercised too.
            if h % 3 == 0:
                code, text = _RETRYABLE
                return SendResult("retryable_error", http_status=429, error_code=code, error_message=text,
                                  retry_after_seconds=30)
            code, text = _PERMANENT[h % len(_PERMANENT)]
            return SendResult("permanent_error", http_status=400, error_code=code, error_message=text)
        return SendResult("accepted", provider_message_id=f"sim.{self.channel}.{message.reference}.{message.attempt}")
