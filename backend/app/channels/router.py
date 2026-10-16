"""Chooses the delivery channel for each recipient and enforces the sending safety rules.

Targeting (who is excluded entirely) and routing (which provider delivers) live together here so the
consent rules exist in exactly one place.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..config import Config
from ..phone import is_valid
from .base import Channel
from .mock import MockChannel

if TYPE_CHECKING:
    from ..models import Customer


@dataclass(frozen=True)
class Route:
    channel: Channel | None
    excluded_reason: str | None = None  # not targeted at all (no message row)
    blocked_reason: str | None = None  # targeted but must not be sent (recorded as a failed message)
    blocked_code: str = ""


class ChannelRouter:
    def __init__(self, config: Config, whatsapp_cloud: Channel | None = None, mpm_sms: Channel | None = None) -> None:
        self.config = config
        self._cloud = whatsapp_cloud
        self._mpm_sms = mpm_sms
        self.failure_rate = 0.0

    # Built lazily so a misconfigured provider never prevents the app (and mock mode) from starting.
    def _cloud_channel(self) -> Channel:
        if self._cloud is None:
            from .whatsapp_cloud import WhatsAppCloudChannel
            self._cloud = WhatsAppCloudChannel(self.config)
        return self._cloud

    def _mpm_sms_channel(self) -> Channel:
        if self._mpm_sms is None:
            from ..integrations.mpm import MpmClient
            from .mpm_sms import MpmSmsChannel
            self._mpm_sms = MpmSmsChannel(MpmClient(self.config))
        return self._mpm_sms

    @property
    def sms_available(self) -> bool:
        return self.config.whatsapp_mode == "mock" or (self.config.mpm_sms_enabled and self.config.mpm_configured)

    def excluded_reason(self, customer: "Customer") -> str | None:
        if customer.account_status != "active":
            return f"account {customer.account_status}"
        if customer.notification_preference == "none":
            return "prefers no messages"
        if customer.notification_preference == "whatsapp" and not customer.whatsapp_opt_in:
            return "no WhatsApp consent"
        if customer.notification_preference == "sms" and not self.sms_available:
            return "SMS via MPM not enabled"
        return None

    def route(self, customer: "Customer") -> Route:
        reason = self.excluded_reason(customer)
        if reason:
            return Route(None, excluded_reason=reason)
        if customer.notification_preference == "sms":
            return self._route_sms(customer)
        return self._route_whatsapp(customer)

    def _route_whatsapp(self, customer: "Customer") -> Route:
        mock = MockChannel("whatsapp", self.failure_rate)
        if not is_valid(customer.phone):
            return Route(mock, blocked_reason="Phone number is not in international (E.164) format",
                         blocked_code="invalid_phone")
        # Demo/simulated customers are never sent to a real provider, whatever the configuration.
        if not self.config.whatsapp_live or customer.source == "demo":
            return Route(mock)
        allowed = self.config.whatsapp_allowlist_disabled or customer.phone in self.config.whatsapp_allowed_recipients
        if not allowed:
            return Route(self._cloud_channel(), blocked_reason="Recipient is not on WHATSAPP_ALLOWED_RECIPIENTS",
                         blocked_code="not_allowlisted")
        return Route(self._cloud_channel())

    def _route_sms(self, customer: "Customer") -> Route:
        if self.config.mpm_sms_enabled and self.config.mpm_configured and customer.source == "mpm":
            channel = self._mpm_sms_channel()
        else:
            channel = MockChannel("sms", self.failure_rate)
        if not is_valid(customer.phone):
            return Route(channel, blocked_reason="Phone number is not in international (E.164) format",
                         blocked_code="invalid_phone")
        return Route(channel)

    def mock_for(self, channel: str) -> Channel:
        return MockChannel(channel, self.failure_rate)

    def status(self) -> dict:
        c = self.config
        return {
            "name": "WhatsApp Business Cloud API",
            "mode": c.whatsapp_mode,
            "live_send_enabled": c.whatsapp_live,
            "configured": c.whatsapp_cloud_configured,
            "api_version": c.whatsapp_api_version,
            "template_language": c.whatsapp_template_language,
            "allowlist": "disabled" if c.whatsapp_allowlist_disabled else f"{len(c.whatsapp_allowed_recipients)} number(s)",
            "webhook_verify_token_set": bool(c.whatsapp_verify_token),
            "webhook_signature_check": bool(c.meta_app_secret),
            "note": ("Live sending is enabled for allow-listed, consenting MPM customers." if c.whatsapp_live else
                     "Mock mode: messages are simulated and never leave PowerChat."),
        }


_router: ChannelRouter | None = None


def configure(router: ChannelRouter) -> None:
    global _router
    _router = router


def get_router() -> ChannelRouter:
    global _router
    if _router is None:
        _router = ChannelRouter(Config())
    return _router
