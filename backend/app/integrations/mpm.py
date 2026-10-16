"""MicroPowerManager REST client.

Endpoints and payloads follow MPM's source (EnAccess/micropowermanager, src/backend):
  POST /api/auth/login             {email, password} -> {access_token, expires_in, ...}   (JWT, guard "api")
  GET  /api/mini-grids             paginated list
  GET  /api/cities                 paginated list; a city belongs to a mini-grid (mini_grid_id)
  GET  /api/people?is_customer=1   paginated; each person includes addresses (phone, is_primary, city_id) and devices
  POST /api/sms/storeandsend       {phone, message} -> queues an SMS through MPM's configured SMS gateway

PowerChat uses a dedicated MPM user (service account) and only reads customer data; it never writes to MPM's
database. Response pagination is parsed defensively because MPM wraps Laravel paginators in ApiResource.
"""
from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from typing import Any

import httpx

from ..config import Config
from ..phone import mask

log = logging.getLogger("powerchat.mpm")


class MpmError(Exception):
    def __init__(self, message: str, status: int | None = None, retryable: bool = False) -> None:
        super().__init__(message)
        self.status, self.retryable = status, retryable


class MpmClient:
    PAGE_SIZE = 100
    MAX_PAGES = 500

    def __init__(self, config: Config, client: httpx.Client | None = None) -> None:
        self.config = config
        self._client = client or httpx.Client(timeout=httpx.Timeout(15.0, connect=5.0))
        self._token: str | None = None
        self._token_expires_at = 0.0

    # ------------------------------------------------------------- transport
    def _url(self, path: str) -> str:
        return f"{self.config.mpm_base_url}{path}"

    def _login(self) -> str:
        if not self.config.mpm_configured:
            raise MpmError("MPM integration is not configured (MPM_BASE_URL, MPM_EMAIL, MPM_PASSWORD)")
        try:
            response = self._client.post(self._url("/api/auth/login"), json={
                "email": self.config.mpm_email, "password": self.config.mpm_password}, headers={"Accept": "application/json"})
        except httpx.HTTPError as exc:
            raise MpmError(f"Could not reach MPM: {type(exc).__name__}", retryable=True) from exc
        if response.status_code in (401, 403):
            raise MpmError("MPM rejected the service-account credentials", status=response.status_code)
        if response.status_code >= 400:
            raise MpmError(f"MPM login failed (HTTP {response.status_code})", status=response.status_code,
                           retryable=response.status_code >= 500)
        body = response.json()
        self._token = body["access_token"]
        # Refresh a minute early so a long sync never uses an expiring token.
        self._token_expires_at = time.monotonic() + max(60, int(body.get("expires_in", 3600)) - 60)
        return self._token

    def _auth_headers(self) -> dict[str, str]:
        if not self._token or time.monotonic() >= self._token_expires_at:
            self._login()
        return {"Authorization": f"Bearer {self._token}", "Accept": "application/json"}

    def request(self, method: str, path: str, **kwargs: Any) -> Any:
        for attempt in (1, 2):
            try:
                response = self._client.request(method, self._url(path), headers=self._auth_headers(), **kwargs)
            except httpx.HTTPError as exc:
                raise MpmError(f"MPM request failed: {type(exc).__name__}", retryable=isinstance(
                    exc, (httpx.ConnectError, httpx.ConnectTimeout))) from exc
            if response.status_code == 401 and attempt == 1:
                self._token = None  # token revoked or expired early: log in again once
                continue
            if response.status_code >= 400:
                message = _error_message(response)
                raise MpmError(f"MPM {method} {path} failed (HTTP {response.status_code}): {message}",
                               status=response.status_code, retryable=response.status_code >= 500)
            return response.json() if response.content else None
        raise MpmError("MPM authentication failed", status=401)

    def paginate(self, path: str, params: dict[str, Any] | None = None) -> Iterator[dict]:
        page = 1
        while page <= self.MAX_PAGES:
            body = self.request("GET", path, params={**(params or {}), "per_page": self.PAGE_SIZE, "page": page})
            items, last_page = _unwrap_page(body)
            yield from items
            if page >= last_page or not items:
                return
            page += 1

    # ------------------------------------------------------------- resources
    def mini_grids(self) -> list[dict]:
        return list(self.paginate("/api/mini-grids"))

    def cities(self) -> list[dict]:
        return list(self.paginate("/api/cities"))

    def customers(self, city_id: int | None = None) -> Iterator[dict]:
        params: dict[str, Any] = {"is_customer": 1}
        if city_id is not None:
            params["city_id"] = city_id
        return self.paginate("/api/people", params)

    def send_sms(self, phone: str, message: str) -> dict:
        log.info("mpm sms storeandsend to=%s", mask(phone))
        body = self.request("POST", "/api/sms/storeandsend", json={"phone": phone, "message": message})
        return (body or {}).get("data", body) or {}

    def test_connection(self) -> dict:
        try:
            self._login()
            grids = self.request("GET", "/api/mini-grids", params={"per_page": 1})
            _, _ = _unwrap_page(grids)
        except MpmError as exc:
            return {"ok": False, "message": str(exc)}
        return {"ok": True, "message": "Logged in to MPM and read mini-grids successfully."}


def _unwrap_page(body: Any) -> tuple[list[dict], int]:
    """Support {"data": paginator}, Laravel resource collections ({"data": [...], "meta": {...}}) and plain lists."""
    if isinstance(body, list):
        return body, 1
    data = body.get("data", body) if isinstance(body, dict) else body
    if isinstance(data, dict) and isinstance(data.get("data"), list):
        return data["data"], int(data.get("last_page") or 1)
    if isinstance(data, list):
        meta = body.get("meta", {}) if isinstance(body, dict) else {}
        return data, int(meta.get("last_page") or 1)
    return [], 1


def _error_message(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.reason_phrase
    return str(body.get("message") or body.get("error") or response.reason_phrase)[:200]


def status(config: Config) -> dict[str, Any]:
    return {
        "name": "MicroPowerManager",
        "configured": config.mpm_configured,
        "base_url": config.mpm_base_url or None,
        "service_account": config.mpm_email or None,
        "sms_via_mpm": config.mpm_sms_enabled and config.mpm_configured,
        "sync_interval_minutes": config.mpm_sync_interval_minutes,
        "mode": "connected_via_api" if config.mpm_configured else "not_configured",
        "note": ("Customers, mini-grids and service areas are read from MPM's REST API with a service account."
                 if config.mpm_configured else
                 "Set MPM_BASE_URL, MPM_EMAIL and MPM_PASSWORD to read customers from MicroPowerManager."),
    }
