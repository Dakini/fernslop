import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.errors import ApiError
from app.main import create_app


class Payload(BaseModel):
    name: str
    count: int = 0


def make_app_with_test_routes() -> FastAPI:
    # A fresh app with throwaway routes, so the real app is never modified.
    test_app = create_app()

    @test_app.post("/api/_test/validate")
    def validate(payload: Payload):
        return {"name": payload.name}

    @test_app.get("/api/_test/query")
    def query(limit: int):
        return {"limit": limit}

    @test_app.get("/api/_test/api-error")
    def api_error():
        raise ApiError(409, "Already exists")

    @test_app.get("/api/_test/unprocessable")
    def unprocessable():
        raise ApiError(422, "Cannot mark care yet")

    @test_app.get("/api/_test/boom")
    def boom():
        raise RuntimeError("secret internal detail")

    return test_app


@pytest.fixture
def routes_client(client):
    return TestClient(make_app_with_test_routes())


@pytest.fixture
def lenient_client(client):
    # Returns the 500 response instead of re-raising the exception.
    return TestClient(make_app_with_test_routes(), raise_server_exceptions=False)


# --- ApiError ----------------------------------------------------------------


def test_api_error_returns_its_status_and_message(routes_client):
    response = routes_client.get("/api/_test/api-error")

    assert response.status_code == 409
    assert response.json() == {"message": "Already exists"}


# --- Validation --------------------------------------------------------------


def test_missing_body_field_returns_400_with_field_and_reason(routes_client):
    response = routes_client.post("/api/_test/validate", json={})

    assert response.status_code == 400
    assert response.json() == {"message": "name: Field required"}


# --- Unknown path and wrong method ------------------------------------------


def test_unknown_path_returns_404_with_message(client):
    response = client.get("/api/nope")

    assert response.status_code == 404
    body = response.json()
    assert list(body) == ["message"]
    assert body["message"] != "Not Found"


def test_wrong_method_on_known_path_returns_405_with_message(client):
    response = client.post("/api/health")

    assert response.status_code == 405
    body = response.json()
    assert list(body) == ["message"]
    assert body["message"] != "Method Not Allowed"


# --- Unhandled exceptions ----------------------------------------------------


def test_unhandled_exception_does_not_leak_traceback_or_exception_text(lenient_client):
    response = lenient_client.get("/api/_test/boom")

    assert "secret internal detail" not in response.text
    assert "Traceback" not in response.text
    assert "RuntimeError" not in response.text


# --- Message shape -----------------------------------------------------------


