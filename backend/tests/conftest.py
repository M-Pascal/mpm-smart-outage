import os
import shutil
import tempfile
from pathlib import Path

# Configure before the app module is imported so the real database is never touched.
_TMP = Path(tempfile.mkdtemp(prefix="powerchat-tests-"))
os.environ["DATABASE_URL"] = f"sqlite:///{(_TMP / 'import.db').as_posix()}"
os.environ["SEED_ON_STARTUP"] = "false"
os.environ["RUN_SCHEDULER"] = "false"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.clock import CLOCK  # noqa: E402
from app.config import Config  # noqa: E402
from app.db import Database  # noqa: E402
from app.main import create_app  # noqa: E402
from app.seed import seed  # noqa: E402
from app.services import monitoring  # noqa: E402


@pytest.fixture(scope="session")
def seeded_template() -> Path:
    path = _TMP / "template.db"
    db = Database(f"sqlite:///{path.as_posix()}")
    db.migrate()
    s = db.SessionLocal()
    seed(s)
    s.close()
    db.engine.dispose()
    return path


@pytest.fixture
def make_client(seeded_template, tmp_path):
    """Build an app on a fresh copy of the seeded DB with custom Config values and an optional channel router."""
    created = []

    def factory(router_factory=None, **config_values) -> TestClient:
        target = tmp_path / f"test{len(created)}.db"
        shutil.copy(seeded_template, target)
        CLOCK.set_offset_seconds(0)
        monitoring.reset_state()
        monitoring.seed_rng(1)
        config = Config(database_url=f"sqlite:///{target.as_posix()}", run_scheduler=False, seed_on_startup=False,
                        **config_values)
        app = create_app(config, channel_router=router_factory(config) if router_factory else None)
        test_client = TestClient(app)
        test_client.__enter__()
        created.append((test_client, app))
        return test_client

    yield factory
    for test_client, app in created:
        test_client.__exit__(None, None, None)
        app.state.db.engine.dispose()
    CLOCK.set_offset_seconds(0)
    from app.channels.router import ChannelRouter, configure
    configure(ChannelRouter(Config()))


@pytest.fixture
def client(make_client) -> TestClient:
    return make_client()


@pytest.fixture
def db(client):
    s = client.app.state.db.SessionLocal()
    yield s
    s.close()


def data(resp, status=200):
    assert resp.status_code == status, resp.text
    return resp.json()["data"]


def advance(client, seconds: float):
    return data(client.post("/api/demo/advance", json={"minutes": seconds / 60}))


def area_id(client, code: str) -> int:
    return next(a["id"] for a in data(client.get("/api/areas")) if a["code"] == code)
