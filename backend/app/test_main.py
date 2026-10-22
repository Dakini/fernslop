import pytest
from fastapi.testclient import TestClient

from app.main import app, create_app
from app.routers import routers
from app.store import Store, get_store, store

HEALTH = "/api/health"
LOCAL_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:8080",
    "http://127.0.0.1:8080",
]


# --- App metadata and routing ------------------------------------------------


def test_app_has_the_expected_title_and_version():
    assert app.title == "Fernslop API"
    assert app.version == "0.1.0"


def test_routers_is_a_list_of_routers_included_by_the_app():
    assert isinstance(routers, list)
    assert routers  # health is the only router today


# --- Health ------------------------------------------------------------------


def test_health_returns_ok(client):
    response = client.get(HEALTH)

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_is_not_in_the_openapi_schema(client):
    response = client.get("/api/openapi.json")

    assert "/api/health" not in response.json()["paths"]
    assert "/health" not in response.json()["paths"]


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


def test_docs_page_is_served_under_the_api_prefix(client):
    response = client.get("/api/docs")

    assert response.status_code == 200


@pytest.mark.parametrize("path", ["/openapi.json", "/docs"])
def test_docs_without_the_api_prefix_return_404(client, path):
    response = client.get(path)

    assert response.status_code == 404


# --- CORS --------------------------------------------------------------------


@pytest.mark.parametrize("origin", LOCAL_ORIGINS)
def test_cors_allows_local_frontend_origins(client, origin):
    response = client.get(HEALTH, headers={"Origin": origin})

    assert response.headers["access-control-allow-origin"] == origin


@pytest.mark.parametrize("origin", LOCAL_ORIGINS)
def test_cors_preflight_allows_methods_and_headers(client, origin):
    response = client.options(
        HEALTH,
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,x-device-id,x-actor-name",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    allowed_methods = {m.strip() for m in response.headers["access-control-allow-methods"].split(",")}
    assert {"GET", "POST", "PATCH", "DELETE"} <= allowed_methods
    allowed_headers = {h.strip().lower() for h in response.headers["access-control-allow-headers"].split(",")}
    assert {"content-type", "x-device-id", "x-actor-name"} <= allowed_headers


def test_cors_rejects_unknown_origin(client):
    response = client.get(HEALTH, headers={"Origin": "https://evil.example"})

    assert "access-control-allow-origin" not in response.headers


def test_cors_preflight_from_unknown_origin_gets_no_allow_origin_header(client):
    response = client.options(
        HEALTH,
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert "access-control-allow-origin" not in response.headers


def test_cors_never_uses_a_wildcard(client):
    response = client.get(HEALTH, headers={"Origin": "http://localhost:5173"})

    assert response.headers["access-control-allow-origin"] != "*"


def test_cors_origins_env_var_overrides_the_defaults(monkeypatch):
    monkeypatch.setenv("FERNSLOP_CORS_ORIGINS", "https://app.example, https://other.example")
    custom = TestClient(create_app())

    allowed = custom.get(HEALTH, headers={"Origin": "https://app.example"})
    second = custom.get(HEALTH, headers={"Origin": "https://other.example"})
    default_origin = custom.get(HEALTH, headers={"Origin": "http://localhost:5173"})

    assert allowed.headers["access-control-allow-origin"] == "https://app.example"
    assert second.headers["access-control-allow-origin"] == "https://other.example"
    assert "access-control-allow-origin" not in default_origin.headers


# --- Store -------------------------------------------------------------------


def test_get_store_returns_the_module_level_store():
    assert get_store() is store
    assert isinstance(get_store(), Store)


def test_store_reset_drops_state_added_after_creation():
    store.scratch = "mutated"

    store.reset()

    assert not hasattr(store, "scratch")


def test_store_state_mutated_in_one_test_is_visible_within_that_test():
    # Pairs with the next test: the mutation made here must not leak into it.
    store.leaky = "from the first test"

    assert store.leaky == "from the first test"


def test_store_state_from_the_previous_test_does_not_leak_into_this_one():
    assert not hasattr(store, "leaky")
