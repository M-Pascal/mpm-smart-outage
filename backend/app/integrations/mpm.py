"""MicroPowerManager REST adapter (prepared, NOT connected).

MPM exposes a Laravel REST API; plugins live in its Laravel package structure.
This adapter is where PowerChat would pull mini-grids, customers and meters, and
receive readings. It is intentionally inactive until MPM_BASE_URL and
MPM_API_TOKEN are configured and the endpoint mapping is verified against a real
MPM instance. Nothing in the demo uses it.
"""
from __future__ import annotations

from typing import Any

import httpx

from ..config import Config


class MpmAdapter:
    # Paths to confirm against the target MPM version before enabling.
    ENDPOINTS = {
        "mini_grids": "/api/mini-grids",
        "customers": "/api/people",
        "meters": "/api/meters",
    }

    def __init__(self, config: Config, client: httpx.Client | None = None) -> None:
        self.config = config
        self._client = client

    @property
    def configured(self) -> bool:
        return bool(self.config.mpm_base_url and self.config.mpm_api_token)

    def status(self) -> dict[str, Any]:
        return {
            "name": "MicroPowerManager",
            "configured": self.configured,
            "connected": False,  # never claimed until a test succeeds and the mapping is verified
            "base_url": self.config.mpm_base_url or None,
            "token_set": bool(self.config.mpm_api_token),
            "mode": "not_connected",
            "note": "Demo uses simulated meters. Set MPM_BASE_URL and MPM_API_TOKEN, then verify the endpoint mapping.",
        }

    def test_connection(self) -> dict[str, Any]:
        if not self.configured:
            return {"ok": False, "message": "MPM integration is not configured (MPM_BASE_URL / MPM_API_TOKEN not set)."}
        client = self._client or httpx.Client(timeout=8.0)
        try:
            resp = client.get(self.config.mpm_base_url.rstrip("/") + self.ENDPOINTS["mini_grids"],
                              headers={"Authorization": f"Bearer {self.config.mpm_api_token}", "Accept": "application/json"})
        except httpx.HTTPError as exc:
            return {"ok": False, "message": f"Could not reach MPM: {exc}"}
        if resp.status_code >= 400:
            return {"ok": False, "message": f"MPM responded with HTTP {resp.status_code}"}
        return {"ok": True, "message": "MPM responded. Verify the data mapping before enabling synchronisation."}
