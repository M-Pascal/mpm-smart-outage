"""Delivery channel contract.

The notification engine only knows this interface, so WhatsApp (mock or Cloud API) and SMS through
MicroPowerManager are interchangeable, and a new channel never requires changes to scheduling or retries.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol

Outcome = Literal["accepted", "retryable_error", "permanent_error", "unknown"]


@dataclass(frozen=True)
class OutboundMessage:
    to: str  # E.164
    template: str  # approved WhatsApp template name
    language: str
    parameters: list[str]  # positional template parameters ({{1}}, {{2}}, ...)
    body: str  # fully rendered text (SMS, mock preview)
    reference: str  # stable id of our message row, used for deterministic mock outcomes and log correlation
    attempt: int = 1


@dataclass(frozen=True)
class SendResult:
    outcome: Outcome
    provider_message_id: str | None = None
    http_status: int | None = None
    error_code: str = ""
    error_message: str = ""
    retry_after_seconds: float | None = None
    extra: dict = field(default_factory=dict)


class Channel(Protocol):
    provider: str  # mock | whatsapp_cloud | mpm_sms
    channel: str  # whatsapp | sms
    simulated: bool

    def send(self, message: OutboundMessage) -> SendResult: ...
