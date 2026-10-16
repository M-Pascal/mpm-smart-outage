"""Environment configuration (infrastructure and secrets only).

Operator-editable preferences (thresholds, notification timing, templates)
live in the database; see services/settings_store.py.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent


def parse_dotenv(text: str) -> dict[str, str]:
    """KEY=VALUE lines; "#" starts a comment unless the value is quoted (tokens may contain "#" only when quoted)."""
    values: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if value[:1] in ("'", '"') and value[1:].find(value[0]) >= 0:
            value = value[1:value.index(value[0], 1)]
        else:
            value = "" if value.startswith("#") else re.split(r"\s#", value, maxsplit=1)[0].strip()
        values[key.strip()] = value
    return values


def _load_dotenv() -> None:
    """Minimal .env loader so no extra dependency is needed. Real environment variables take precedence."""
    env_file = BACKEND_DIR / ".env"
    if not env_file.exists():
        return
    for key, value in parse_dotenv(env_file.read_text(encoding="utf-8")).items():
        os.environ.setdefault(key, value)


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    return default if raw is None else raw.strip().lower() in {"1", "true", "yes", "on"}


def _list(name: str, default: list[str]) -> list[str]:
    raw = os.getenv(name)
    return [x.strip() for x in raw.split(",") if x.strip()] if raw else default


@dataclass
class Config:
    database_url: str = f"sqlite:///{(BACKEND_DIR / 'powerchat.db').as_posix()}"
    tick_seconds: float = 3.0
    run_scheduler: bool = True
    seed_on_startup: bool = True
    cors_origins: list[str] = field(default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"])

    # WhatsApp Business Cloud API. "mock" never contacts Meta. "cloud" sends real messages, but only when
    # live sending is explicitly enabled, and only to allow-listed numbers unless the allowlist is disabled.
    whatsapp_mode: str = "mock"
    whatsapp_live_send_enabled: bool = False
    whatsapp_allowed_recipients: list[str] = field(default_factory=list)
    whatsapp_allowlist_disabled: bool = False
    whatsapp_access_token: str = ""
    whatsapp_phone_number_id: str = ""
    whatsapp_business_account_id: str = ""
    whatsapp_verify_token: str = ""
    meta_app_secret: str = ""
    whatsapp_api_version: str = "v26.0"
    whatsapp_template_language: str = "en"

    # MicroPowerManager REST API (service account; JWT via POST /api/auth/login).
    mpm_base_url: str = ""
    mpm_email: str = ""
    mpm_password: str = ""
    mpm_default_country_code: str = "250"
    mpm_sms_enabled: bool = False  # deliver SMS-preference customers through MPM's own SMS pipeline
    mpm_sync_interval_minutes: int = 0  # 0 = manual sync only

    # Shared secret for meter telemetry pushed into PowerChat (X-PowerChat-Key header).
    telemetry_api_key: str = ""

    @property
    def whatsapp_cloud_configured(self) -> bool:
        return bool(self.whatsapp_access_token and self.whatsapp_phone_number_id)

    @property
    def whatsapp_live(self) -> bool:
        return self.whatsapp_mode == "cloud" and self.whatsapp_live_send_enabled and self.whatsapp_cloud_configured

    @property
    def mpm_configured(self) -> bool:
        return bool(self.mpm_base_url and self.mpm_email and self.mpm_password)

    @classmethod
    def from_env(cls) -> "Config":
        _load_dotenv()
        base = cls()
        return cls(
            database_url=os.getenv("DATABASE_URL", base.database_url),
            tick_seconds=float(os.getenv("SCHEDULER_TICK_SECONDS", base.tick_seconds)),
            run_scheduler=_bool("RUN_SCHEDULER", True),
            seed_on_startup=_bool("SEED_ON_STARTUP", True),
            cors_origins=_list("CORS_ORIGINS", base.cors_origins),
            whatsapp_mode=os.getenv("WHATSAPP_MODE", "mock").strip().lower(),
            whatsapp_live_send_enabled=_bool("WHATSAPP_LIVE_SEND_ENABLED", False),
            whatsapp_allowed_recipients=_list("WHATSAPP_ALLOWED_RECIPIENTS", []),
            whatsapp_allowlist_disabled=_bool("WHATSAPP_ALLOWLIST_DISABLED", False),
            whatsapp_access_token=os.getenv("WHATSAPP_ACCESS_TOKEN", ""),
            whatsapp_phone_number_id=os.getenv("WHATSAPP_PHONE_NUMBER_ID", ""),
            whatsapp_business_account_id=os.getenv("WHATSAPP_BUSINESS_ACCOUNT_ID", ""),
            whatsapp_verify_token=os.getenv("WHATSAPP_VERIFY_TOKEN", ""),
            meta_app_secret=os.getenv("META_APP_SECRET", ""),
            whatsapp_api_version=os.getenv("WHATSAPP_API_VERSION", base.whatsapp_api_version),
            whatsapp_template_language=os.getenv("WHATSAPP_TEMPLATE_LANGUAGE", "en"),
            mpm_base_url=os.getenv("MPM_BASE_URL", "").rstrip("/"),
            mpm_email=os.getenv("MPM_EMAIL", ""),
            mpm_password=os.getenv("MPM_PASSWORD", ""),
            mpm_default_country_code=os.getenv("MPM_DEFAULT_COUNTRY_CODE", "250").lstrip("+"),
            mpm_sms_enabled=_bool("MPM_SMS_ENABLED", False),
            mpm_sync_interval_minutes=int(os.getenv("MPM_SYNC_INTERVAL_MINUTES", "0") or 0),
            telemetry_api_key=os.getenv("TELEMETRY_API_KEY", ""),
        )
