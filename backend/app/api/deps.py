from __future__ import annotations

from collections.abc import Iterator

from fastapi import Request
from sqlalchemy.orm import Session

from ..services import settings_store


def get_db(request: Request) -> Iterator[Session]:
    yield from request.app.state.db.session()


def actor(db: Session) -> str:
    return settings_store.get_section(db, "general").operator_name
