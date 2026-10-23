import pytest
from fastapi.testclient import TestClient

from app.main import create_app

HEALTH = "/api/health"
LOCAL_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]


# --- App metadata and routing ------------------------------------------------


# --- Health ------------------------------------------------------------------


def test_health_returns_ok(client):
    response = client.get(HEALTH)

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.parametrize("path", ["/", "/health", "/rooms"])
def test_paths_without_the_api_prefix_are_not_served(client, path):
    response = client.get(path)

    assert response.status_code == 404
    assert response.json()["message"]


# --- Generated docs ----------------------------------------------------------


def test_openapi_json_is_served_under_the_api_prefix(client):
    response = client.get("/api/openapi.json")

    assert response.status_code == 200
    assert response.json()["info"]["title"] == "Fernslop API"


@pytest.mark.parametrize("path", ["/api/docs", "/api/redoc", "/api/openapi.json"])
def test_api_docs_flag_off_hides_docs_with_404(reset_store, monkeypatch, path):
    monkeypatch.setenv("FERNSLOP_API_DOCS", "0")
    client = TestClient(create_app())

    response = client.get(path)

    assert response.status_code == 404


# --- CORS --------------------------------------------------------------------


@pytest.mark.parametrize("origin", LOCAL_ORIGINS)
def test_cors_allows_local_frontend_origins(client, origin):
    response = client.get(HEALTH, headers={"Origin": origin})

    assert response.headers["access-control-allow-origin"] == origin


def test_cors_rejects_unknown_origin(client):
    response = client.get(HEALTH, headers={"Origin": "https://evil.example"})

    assert "access-control-allow-origin" not in response.headers
