"""Environment configuration (infrastructure and secrets only).

Operator-editable preferences (thresholds, notification timing, templates)
live in the database; see services/settings_store.py.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv() -> None:
    """Minimal .env loader (KEY=VALUE lines) so no extra dependency is needed."""
    env_file = BACKEND_DIR / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


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

    # WhatsApp Business Cloud API (future). Not used by the simulator.
    whatsapp_access_token: str = ""
    whatsapp_phone_number_id: str = ""
    whatsapp_business_account_id: str = ""
    whatsapp_api_version: str = "v21.0"

    # MicroPowerManager REST API (future).
    mpm_base_url: str = ""
    mpm_api_token: str = ""

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
            whatsapp_access_token=os.getenv("WHATSAPP_ACCESS_TOKEN", ""),
            whatsapp_phone_number_id=os.getenv("WHATSAPP_PHONE_NUMBER_ID", ""),
            whatsapp_business_account_id=os.getenv("WHATSAPP_BUSINESS_ACCOUNT_ID", ""),
            whatsapp_api_version=os.getenv("WHATSAPP_API_VERSION", "v21.0"),
            mpm_base_url=os.getenv("MPM_BASE_URL", ""),
            mpm_api_token=os.getenv("MPM_API_TOKEN", ""),
        )
