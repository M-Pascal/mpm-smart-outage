"""Database engine and session handling.

SQLite for the prototype. The models only use portable SQLAlchemy types, so
switching DATABASE_URL to PostgreSQL (postgresql+psycopg://...) works without code
changes; add Alembic migrations before production use.
"""
from __future__ import annotations

import threading
from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


# Serialises the scheduler tick with API writes that touch the same rows.
WRITE_LOCK = threading.RLock()


class Database:
    def __init__(self, url: str) -> None:
        kwargs: dict = {}
        if url.startswith("sqlite"):
            kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
        self.engine = create_engine(url, **kwargs)
        if url.startswith("sqlite"):
            @event.listens_for(self.engine, "connect")
            def _pragmas(conn, _):  # noqa: ANN001
                cur = conn.cursor()
                cur.execute("PRAGMA foreign_keys=ON")
                if ":memory:" not in url:
                    cur.execute("PRAGMA journal_mode=WAL")
                cur.close()
        self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False)

    def create_all(self) -> None:
        from . import models  # noqa: F401  (register models)

        Base.metadata.create_all(self.engine)

    def drop_all(self) -> None:
        from . import models  # noqa: F401

        Base.metadata.drop_all(self.engine)

    def session(self) -> Iterator[Session]:
        db = self.SessionLocal()
        try:
            yield db
        finally:
            db.close()
