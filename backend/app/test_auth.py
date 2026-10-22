import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.auth import Actor, get_actor
from app.errors import register_error_handlers

DEVICE_ID = "7b1f0c2e-5d3a-4c6b-9e2f-1a2b3c4d5e6f"
ACTOR_PATH = "/actor"
OPEN_PATH = "/open"


def make_app() -> FastAPI:
    app = FastAPI()
    register_error_handlers(app)

    @app.post(ACTOR_PATH)
    def echo_actor(actor: Actor = Depends(get_actor)):  # noqa: B008 - FastAPI idiom
        return actor

    @app.post(OPEN_PATH)
    def open_route():
        return {"ok": True}

    return app


@pytest.fixture
def actor_client():
    return TestClient(make_app())


def actor_headers(**overrides):
    headers = {"X-Device-Id": DEVICE_ID, "X-Actor-Name": "Anonymous%20Hedgehog"}
    headers.update(overrides)
    return {key: value for key, value in headers.items() if value is not None}


def post_actor(client, **overrides):
    return client.post(ACTOR_PATH, headers=actor_headers(**overrides))


def assert_rejected(response, message):
    assert response.status_code == 400
    assert response.json() == {"message": message}


# --- Happy path --------------------------------------------------------------


def test_valid_headers_give_the_decoded_actor(actor_client):
    response = post_actor(actor_client)

    assert response.status_code == 200
    assert response.json() == {"device_id": DEVICE_ID, "name": "Anonymous Hedgehog"}


def test_name_is_percent_decoded_as_utf8(actor_client):
    response = post_actor(actor_client, **{"X-Actor-Name": "Zo%C3%AB%20%F0%9F%8C%BF"})

    assert response.status_code == 200
    assert response.json()["name"] == "Zoë 🌿"


# --- Device id rejections ----------------------------------------------------


@pytest.mark.parametrize("value", [None, "   "])
def test_missing_or_blank_device_id_is_rejected(actor_client, value):
    response = post_actor(actor_client, **{"X-Device-Id": value})

    assert_rejected(response, "X-Device-Id header is required.")


# --- Actor name rejections ---------------------------------------------------


@pytest.mark.parametrize("value", [None, "%20%20"])
def test_missing_or_blank_name_is_rejected(actor_client, value):
    response = post_actor(actor_client, **{"X-Actor-Name": value})

    assert_rejected(response, "X-Actor-Name header is required.")


def test_name_of_41_characters_is_rejected(actor_client):
    response = post_actor(actor_client, **{"X-Actor-Name": "n" * 41})

    assert_rejected(response, "X-Actor-Name must be at most 40 characters.")


# --- Precedence and shape ----------------------------------------------------


# --- Opt-in per route --------------------------------------------------------


# --- CORS preflight ----------------------------------------------------------


