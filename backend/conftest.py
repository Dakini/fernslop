import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app import sql_store
from app.main import app
from app.store import DATABASE_URL_ENV, close_stores

# Set to a postgres URL to run the whole suite on Postgres instead of in-memory SQLite.
TEST_DATABASE_URL_ENV = "FERNSLOP_TEST_DATABASE_URL"
TEST_DATABASE_URL = os.environ.get(TEST_DATABASE_URL_ENV) or None

requires_postgres = pytest.mark.skipif(
    TEST_DATABASE_URL is None, reason=f"set {TEST_DATABASE_URL_ENV} to a postgres URL to run this test"
)


def _empty_database(url: str) -> None:
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    engine.dispose()


@pytest.fixture(autouse=True)
def reset_store(monkeypatch):
    """Every test gets its own fresh, seeded database; ./fernslop.db is never touched.

    By default that is an in-memory SQLite database. With FERNSLOP_TEST_DATABASE_URL set, the database
    is emptied before the test and every ``SqlStore("sqlite://")`` a test builds uses it instead.
    """
    engines = []
    if TEST_DATABASE_URL:
        _empty_database(TEST_DATABASE_URL)
        real_make_engine = sql_store._make_engine

        def make_engine(url):
            if url == "sqlite://":
                _empty_database(TEST_DATABASE_URL)  # a new in-memory store is empty, so is this one
                url = TEST_DATABASE_URL
            engines.append(real_make_engine(url))
            return engines[-1]

        monkeypatch.setattr(sql_store, "_make_engine", make_engine)
        monkeypatch.setenv(DATABASE_URL_ENV, TEST_DATABASE_URL)
    else:
        monkeypatch.setenv(DATABASE_URL_ENV, "sqlite://")
    close_stores()
    yield
    close_stores()
    for engine in engines:  # stores a test built itself; free their connections
        engine.dispose()


@pytest.fixture
def client(reset_store):
    return TestClient(app)
