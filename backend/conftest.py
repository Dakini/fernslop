import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.store import get_store, store


@pytest.fixture(autouse=True)
def reset_store():
    store.reset()
    get_store().reset()
    yield
    store.reset()
    get_store().reset()


@pytest.fixture
def client(reset_store):
    return TestClient(app)
