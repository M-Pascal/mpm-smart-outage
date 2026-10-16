"""Database engine and session handling.

SQLite for local development and tests; PostgreSQL (e.g. Render) or MySQL
(MPM's database engine) for deployment via DATABASE_URL. The schema is managed by the
Alembic migrations in backend/migrations and applied automatically at startup.
"""
from __future__ import annotations

import threading
from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"

# Serialises the scheduler tick with API writes that touch the same rows.
WRITE_LOCK = threading.RLock()


class Database:
    def __init__(self, url: str) -> None:
        from .config import normalize_database_url

        url = normalize_database_url(url)
        kwargs: dict = {}
        if url.startswith("sqlite"):
            kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
        else:
            # Managed databases close idle connections; check before use instead of failing a request.
            kwargs["pool_pre_ping"] = True
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

    def migrate(self) -> None:
        """Bring the schema to the latest Alembic revision.

        Databases created before migrations existed (tables present, no alembic_version) are stamped at
        the baseline first so only the newer revisions run against them.
        """
        from alembic import command
        from alembic.config import Config as AlembicConfig
        from sqlalchemy import inspect

        cfg = AlembicConfig(str(MIGRATIONS_DIR.parent / "alembic.ini"))
        cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
        tables = set(inspect(self.engine).get_table_names())
        sqlite = self.engine.dialect.name == "sqlite"
        with self.engine.connect() as connection:
            if sqlite:
                # SQLite ALTERs rebuild tables; FK enforcement must be off, and the pragma only works outside a transaction.
                connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
                connection.commit()
            with connection.begin():
                cfg.attributes["connection"] = connection
                if tables and "alembic_version" not in tables:
                    command.stamp(cfg, "0001")
                command.upgrade(cfg, "head")
            if sqlite:
                connection.exec_driver_sql("PRAGMA foreign_keys=ON")
                connection.commit()

    def drop_all(self) -> None:
        from sqlalchemy import text

        from . import models  # noqa: F401

        Base.metadata.drop_all(self.engine)
        with self.engine.begin() as connection:
            connection.execute(text("DROP TABLE IF EXISTS alembic_version"))

    def session(self) -> Iterator[Session]:
        db = self.SessionLocal()
        try:
            yield db
        finally:
            db.close()
