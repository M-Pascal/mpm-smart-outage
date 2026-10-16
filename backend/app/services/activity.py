from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from ..clock import now
from ..models import ActivityLog


def log(db: Session, type_: str, message: str, *, severity: str = "info", entity_type: str | None = None,
        entity_id: int | None = None, operator_alert: bool = False, ts: datetime | None = None) -> ActivityLog:
    entry = ActivityLog(type=type_, message=message, severity=severity, entity_type=entity_type,
                        entity_id=entity_id, operator_alert=operator_alert, ts=ts or now())
    db.add(entry)
    return entry
