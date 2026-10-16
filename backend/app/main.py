"""PowerChat API: `uvicorn app.main:app --reload` (from the backend folder)."""
from __future__ import annotations

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .api import comms, core, integrations, outages
from .channels.router import ChannelRouter, configure as configure_channels
from .config import Config
from .db import WRITE_LOCK, Database
from .errors import AppError
from .seed import is_seeded, seed
from .services import engine, monitoring, settings_store

log = logging.getLogger("powerchat")

DESCRIPTION = """
Outage management and customer communication for mini-grid operators.

* **Mock messaging by default:** WhatsApp messages are simulated unless `WHATSAPP_MODE=cloud` and
  `WHATSAPP_LIVE_SEND_ENABLED=true` are set, and then only to allow-listed, consenting MPM customers.
* Customers, mini-grids and service areas can be synchronised from MicroPowerManager's REST API.
* Responses use `{"data": ...}`; errors use `{"error": {"code", "message", "details"}}`.
* Times are UTC ISO-8601 (`Z`). The demo clock can be moved forward with `/api/demo/advance`.
"""


async def _scheduler_loop(app: FastAPI) -> None:
    db_wrapper: Database = app.state.db
    config: Config = app.state.config
    last_sync = 0.0
    while True:
        await asyncio.sleep(config.tick_seconds)
        try:
            await asyncio.to_thread(_tick_once, db_wrapper)
        except Exception:  # keep the scheduler alive
            log.exception("scheduler tick failed")
        if config.mpm_configured and config.mpm_sync_interval_minutes > 0:
            loop_time = asyncio.get_running_loop().time()
            if loop_time - last_sync >= config.mpm_sync_interval_minutes * 60:
                last_sync = loop_time
                try:
                    await asyncio.to_thread(_sync_mpm, db_wrapper, config)
                except Exception:
                    log.exception("scheduled MPM sync failed")


def _tick_once(db_wrapper: Database) -> None:
    db = db_wrapper.SessionLocal()
    try:
        simulate = settings_store.get_section(db, "demo").auto_tick
        engine.tick(db, simulate=simulate)
    finally:
        db.close()


def _sync_mpm(db_wrapper: Database, config: Config) -> None:
    from .integrations.mpm import MpmClient
    from .services import mpm_sync

    db = db_wrapper.SessionLocal()
    try:
        mpm_sync.sync(db, MpmClient(config))
    finally:
        db.close()


def create_app(config: Config | None = None, channel_router: ChannelRouter | None = None) -> FastAPI:
    config = config or Config.from_env()
    if config.whatsapp_mode not in ("mock", "cloud"):
        raise ValueError("WHATSAPP_MODE must be 'mock' or 'cloud'")
    configure_channels(channel_router or ChannelRouter(config))
    database = Database(config.database_url)

    def init_database() -> None:
        database.migrate()
        db = database.SessionLocal()
        try:
            if config.seed_on_startup and not is_seeded(db):
                seed(db)
            engine.load_clock(db)
        finally:
            db.close()

    def reset_database() -> None:
        with WRITE_LOCK:
            database.drop_all()
            monitoring.reset_state()
            from .clock import CLOCK
            CLOCK.set_offset_seconds(0)
            database.migrate()
            db = database.SessionLocal()
            try:
                seed(db)
                engine.load_clock(db)
            finally:
                db.close()

    init_database()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        task = asyncio.create_task(_scheduler_loop(app)) if config.run_scheduler else None
        try:
            yield
        finally:
            if task:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

    app = FastAPI(title="PowerChat API", version="1.0.0", description=DESCRIPTION, lifespan=lifespan)
    app.state.config = config
    app.state.db = database
    app.state.reset_database = reset_database
    app.add_middleware(CORSMiddleware, allow_origins=config.cors_origins, allow_methods=["*"], allow_headers=["*"])
    for r in (core.router, outages.router, comms.router, integrations.router):
        app.include_router(r)

    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError):
        return JSONResponse(status_code=exc.status, content={"error": {"code": exc.code, "message": exc.message,
                                                                       "details": exc.details}})

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        details = [{"field": ".".join(str(p) for p in e["loc"] if p not in ("body", "query")),
                    "message": e["msg"].removeprefix("Value error, ")} for e in exc.errors()]
        first = details[0] if details else {"field": None, "message": "Invalid input"}
        message = f"{first['field']}: {first['message']}" if first["field"] else first["message"]
        return JSONResponse(status_code=422, content={"error": {"code": "validation_error", "message": message,
                                                                "details": details}})

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException):
        return JSONResponse(status_code=exc.status_code, content={"error": {
            "code": "not_found" if exc.status_code == 404 else "http_error", "message": str(exc.detail), "details": []}})

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception):
        log.exception("unhandled error", exc_info=exc)
        return JSONResponse(status_code=500, content={"error": {"code": "internal_error",
                                                                "message": "Something went wrong on the server.",
                                                                "details": []}})

    return app


app = create_app()
