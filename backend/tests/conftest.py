import os

os.environ["RATE_LIMIT_ENABLED"] = "false"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.core.config import settings
from app.database.session import Base, get_db
from main import app

END = "2026-10-30"


def _engine():
    e = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(e)
    return e


@pytest.fixture(scope="session", autouse=True)
def _artifacts(tmp_path_factory):
    settings.artifacts_dir = str(tmp_path_factory.mktemp("artifacts"))


@pytest.fixture()
def client():
    e = _engine()
    Session = sessionmaker(bind=e)

    def override():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture(scope="module")
def seeded_db():
    from app.services.seed import seed
    e = _engine()
    db = sessionmaker(bind=e)()
    seed(db, days=3, interval_s=600, end=END)
    yield db
    db.close()


@pytest.fixture(scope="module")
def api():
    """Authenticated admin client against a seeded in-memory DB (SIMULATED data)."""
    e = _engine()
    Session = sessionmaker(bind=e)

    def override():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override
    c = TestClient(app)
    c.post("/api/v1/auth/register", json={"email": "admin@x.io", "password": "password123"})
    tok = c.post("/api/v1/auth/login", data={"username": "admin@x.io", "password": "password123"}).json()["access_token"]
    c.headers.update({"Authorization": f"Bearer {tok}"})
    r = c.post("/api/v1/admin/seed", json={"days": 3, "interval_s": 600})
    assert r.status_code == 200, r.text
    yield c
    app.dependency_overrides.clear()
