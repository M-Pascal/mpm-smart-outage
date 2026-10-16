"""WhatsApp Business Cloud API client (prepared, NOT wired into sending).

The prototype only uses the in-app simulator. To go live:
  1. Register each template (services/templates.py) in WhatsApp Manager and get approval.
  2. Set WHATSAPP_ACCESS_TOKEN / WHATSAPP_PHONE_NUMBER_ID.
  3. Replace the simulated outcome in services/notifications.send_job with
     WhatsAppCloudClient.send_template, keeping the consent checks.
  4. Receive delivery statuses on a webhook (verify X-Hub-Signature-256).

WhatsApp *Channels* have no documented publishing API, so PowerChat only
generates Channel-ready text for an operator to publish manually.
"""
from __future__ import annotations

from typing import Any

import httpx

from ..config import Config


class WhatsAppCloudClient:
    def __init__(self, config: Config, client: httpx.Client | None = None) -> None:
        self.config = config
        self._client = client or httpx.Client(timeout=10.0)

    @property
    def configured(self) -> bool:
        return bool(self.config.whatsapp_access_token and self.config.whatsapp_phone_number_id)

    @staticmethod
    def build_template_payload(to_phone: str, template: str, params: list[str], language: str = "en") -> dict[str, Any]:
        return {
            "messaging_product": "whatsapp",
            "to": to_phone.lstrip("+"),
            "type": "template",
            "template": {"name": template, "language": {"code": language},
                         "components": [{"type": "body", "parameters": [{"type": "text", "text": p} for p in params]}]},
        }

    def send_template(self, to_phone: str, template: str, params: list[str], language: str = "en") -> dict[str, Any]:
        if not self.configured:
            raise RuntimeError("WhatsApp Cloud API is not configured")
        url = (f"https://graph.facebook.com/{self.config.whatsapp_api_version}/"
               f"{self.config.whatsapp_phone_number_id}/messages")
        resp = self._client.post(url, json=self.build_template_payload(to_phone, template, params, language),
                                 headers={"Authorization": f"Bearer {self.config.whatsapp_access_token}"})
        resp.raise_for_status()
        return resp.json()


def status(config: Config) -> dict[str, Any]:
    return {
        "name": "WhatsApp Business Cloud API",
        "configured": bool(config.whatsapp_access_token and config.whatsapp_phone_number_id),
        "connected": False,
        "token_set": bool(config.whatsapp_access_token),
        "phone_number_id_set": bool(config.whatsapp_phone_number_id),
        "api_version": config.whatsapp_api_version,
        "mode": "simulation",
        "note": "All messages are simulated. No real customer is contacted.",
    }
