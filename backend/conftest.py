import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.store import DATABASE_URL_ENV, close_stores


@pytest.fixture(autouse=True)
def reset_store(monkeypatch):
    """Every test gets its own fresh, seeded, in-memory database; ./fernslop.db is never touched."""
    monkeypatch.setenv(DATABASE_URL_ENV, "sqlite://")
    close_stores()
    yield
    close_stores()


@pytest.fixture
def client(reset_store):
    return TestClient(app)
