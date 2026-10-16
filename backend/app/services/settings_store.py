"""Operator-editable application settings, stored in the app_settings table."""
from __future__ import annotations

from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from ..models import AppSetting


class GeneralSettings(BaseModel):
    organization_name: str = Field("PowerChat Energy", min_length=1, max_length=80)
    timezone: str = "Africa/Kigali"
    operator_name: str = Field("Admin Operator", min_length=1, max_length=80)
    date_format: str = "d MMMM yyyy"

    @field_validator("timezone")
    @classmethod
    def _tz(cls, v: str) -> str:
        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError(f"unknown time zone '{v}'")
        return v


class NotificationSettings(BaseModel):
    default_reminder_offsets: list[int] = Field(default_factory=lambda: [1440, 360, 60])
    send_notice_on_publish: bool = True
    auto_notify_unexpected: bool = True
    restoration_min_customers: int = Field(5, ge=0, description="Suggest a restoration announcement at or above this many affected customers")
    simulated_failure_rate: float = Field(0.08, ge=0, le=0.5)

    @field_validator("default_reminder_offsets")
    @classmethod
    def _offsets(cls, v: list[int]) -> list[int]:
        if any(o <= 0 or o > 60 * 24 * 14 for o in v):
            raise ValueError("reminder offsets must be between 1 minute and 14 days before the start")
        return sorted(set(v), reverse=True)


class DetectionSettings(BaseModel):
    outage_voltage_max: float = Field(50, ge=0, le=150)
    low_voltage_max: float = Field(196, ge=100, le=230)
    restore_voltage_min: float = Field(180, ge=50, le=230)
    confirm_readings: int = Field(2, ge=1, le=10)
    verification_seconds: int = Field(6, ge=0, le=3600)
    min_meters_for_area_outage: int = Field(2, ge=2, le=50)
    stale_after_seconds: int = Field(20, ge=5, le=86400)
    mpm_stale_after_seconds: int = Field(1800, ge=60, le=7 * 86400)
    # Off by default: customers are alerted only after an operator verifies the incident.
    auto_confirm: bool = False
    comm_loss_ratio: float = Field(0.5, ge=0.1, le=1.0)
    auto_resolve_on_restore: bool = True


class DemoSettings(BaseModel):
    clock_offset_seconds: float = 0
    auto_tick: bool = True


SECTIONS: dict[str, type[BaseModel]] = {
    "general": GeneralSettings,
    "notifications": NotificationSettings,
    "detection": DetectionSettings,
    "demo": DemoSettings,
}


def get_section(db: Session, section: str) -> Any:
    model = SECTIONS[section]
    row = db.get(AppSetting, section)
    return model(**(row.value if row else {}))


def get_all(db: Session) -> dict[str, dict[str, Any]]:
    return {name: get_section(db, name).model_dump() for name in SECTIONS}


def update_section(db: Session, section: str, values: dict[str, Any]) -> BaseModel:
    model = SECTIONS[section]
    merged = {**get_section(db, section).model_dump(), **values}
    validated = model(**merged)
    if section == "detection" and validated.restore_voltage_min <= validated.outage_voltage_max:
        raise ValueError("restore voltage must be higher than the outage voltage threshold")
    row = db.get(AppSetting, section)
    if row is None:
        db.add(AppSetting(key=section, value=validated.model_dump()))
    else:
        row.value = validated.model_dump()
    db.flush()
    return validated
