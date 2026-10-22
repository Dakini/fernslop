import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.auth import Actor, get_actor
from app.errors import register_error_handlers
from app.main import create_app

DEVICE_ID = "7b1f0c2e-5d3a-4c6b-9e2f-1a2b3c4d5e6f"
ACTOR_PATH = "/actor"
OPEN_PATH = "/open"
ORIGIN = "http://localhost:5173"


def make_app() -> FastAPI:
    app = FastAPI()
    register_error_handlers(app)

    @app.post(ACTOR_PATH)
    def echo_actor(actor: Actor = Depends(get_actor)):
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


def test_plain_ascii_name_passes_through_unchanged(actor_client):
    response = post_actor(actor_client, **{"X-Actor-Name": "Fern"})

    assert response.json()["name"] == "Fern"


def test_literal_plus_in_name_stays_a_plus(actor_client):
    response = post_actor(actor_client, **{"X-Actor-Name": "a+b%20c"})

    assert response.json()["name"] == "a+b c"


def test_name_is_trimmed_but_inner_whitespace_is_kept(actor_client):
    response = post_actor(actor_client, **{"X-Actor-Name": "%20%20Fern%20Fan%20"})

    assert response.json()["name"] == "Fern Fan"


def test_device_id_is_trimmed(actor_client):
    response = post_actor(actor_client, **{"X-Device-Id": "  abc  "})

    assert response.status_code == 200
    assert response.json()["device_id"] == "abc"


def test_header_names_are_case_insensitive(actor_client):
    response = actor_client.post(ACTOR_PATH, headers={"x-device-id": DEVICE_ID, "x-actor-name": "Fern"})

    assert response.status_code == 200
    assert response.json() == {"device_id": DEVICE_ID, "name": "Fern"}


def test_device_id_need_not_be_a_uuid(actor_client):
    response = post_actor(actor_client, **{"X-Device-Id": "pending"})

    assert response.status_code == 200
    assert response.json()["device_id"] == "pending"


def test_same_device_id_may_use_different_names(actor_client):
    first = post_actor(actor_client, **{"X-Actor-Name": "One"})
    second = post_actor(actor_client, **{"X-Actor-Name": "Two"})

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["name"] == "Two"


# --- Device id rejections ----------------------------------------------------


@pytest.mark.parametrize("value", [None, "", "   "])
def test_missing_or_blank_device_id_is_rejected(actor_client, value):
    response = post_actor(actor_client, **{"X-Device-Id": value})

    assert_rejected(response, "X-Device-Id header is required.")


def test_device_id_of_64_characters_is_accepted(actor_client):
    response = post_actor(actor_client, **{"X-Device-Id": "d" * 64})

    assert response.status_code == 200
    assert response.json()["device_id"] == "d" * 64


def test_device_id_of_65_characters_is_rejected(actor_client):
    response = post_actor(actor_client, **{"X-Device-Id": "d" * 65})

    assert_rejected(response, "X-Device-Id must be at most 64 characters.")


def test_device_id_length_is_counted_after_trimming(actor_client):
    response = post_actor(actor_client, **{"X-Device-Id": " " + "d" * 64 + " "})

    assert response.status_code == 200


# --- Actor name rejections ---------------------------------------------------


@pytest.mark.parametrize("value", [None, "", "%20%20", "%09", "   "])
def test_missing_or_blank_name_is_rejected(actor_client, value):
    response = post_actor(actor_client, **{"X-Actor-Name": value})

    assert_rejected(response, "X-Actor-Name header is required.")


@pytest.mark.parametrize("value", ["%FF", "%C3", "Fern%C3"])
def test_name_that_is_not_valid_utf8_is_rejected(actor_client, value):
    response = post_actor(actor_client, **{"X-Actor-Name": value})

    assert_rejected(response, "X-Actor-Name is not valid percent-encoded UTF-8.")


@pytest.mark.parametrize("value", ["%00", "a%00b", "a%0Ab", "Fern%7F", "a%09b"])
def test_name_with_a_control_character_is_rejected(actor_client, value):
    response = post_actor(actor_client, **{"X-Actor-Name": value})

    assert_rejected(response, "X-Actor-Name contains invalid characters.")


def test_name_of_40_characters_is_accepted(actor_client):
    response = post_actor(actor_client, **{"X-Actor-Name": "n" * 40})

    assert response.status_code == 200
    assert response.json()["name"] == "n" * 40


def test_name_of_41_characters_is_rejected(actor_client):
    response = post_actor(actor_client, **{"X-Actor-Name": "n" * 41})

    assert_rejected(response, "X-Actor-Name must be at most 40 characters.")


def test_name_length_is_counted_after_trimming(actor_client):
    response = post_actor(actor_client, **{"X-Actor-Name": "%20" + "n" * 40 + "%20"})

    assert response.status_code == 200


def test_40_emoji_name_is_accepted_even_though_it_is_over_120_bytes_encoded(actor_client):
    encoded = "%F0%9F%8C%BF" * 40

    response = post_actor(actor_client, **{"X-Actor-Name": encoded})

    assert len(encoded) > 120
    assert response.status_code == 200
    assert response.json()["name"] == "🌿" * 40


def test_41_emoji_name_is_rejected(actor_client):
    response = post_actor(actor_client, **{"X-Actor-Name": "%F0%9F%8C%BF" * 41})

    assert_rejected(response, "X-Actor-Name must be at most 40 characters.")


# --- Precedence and shape ----------------------------------------------------


def test_when_both_headers_are_bad_the_device_id_message_wins(actor_client):
    response = post_actor(actor_client, **{"X-Device-Id": None, "X-Actor-Name": "%FF"})

    assert_rejected(response, "X-Device-Id header is required.")


def test_no_headers_at_all_reports_the_device_id(actor_client):
    response = actor_client.post(ACTOR_PATH)

    assert_rejected(response, "X-Device-Id header is required.")


@pytest.mark.parametrize(
    "overrides",
    [
        {"X-Device-Id": None},
        {"X-Device-Id": "d" * 65},
        {"X-Actor-Name": None},
        {"X-Actor-Name": "%FF"},
        {"X-Actor-Name": "%00"},
        {"X-Actor-Name": "n" * 41},
    ],
)
def test_rejection_bodies_have_a_message_and_no_detail(actor_client, overrides):
    response = post_actor(actor_client, **overrides)

    assert response.status_code == 400
    assert "detail" not in response.json()
    assert list(response.json()) == ["message"]


def test_missing_actor_is_rejected_before_the_route_body_runs():
    app = FastAPI()
    register_error_handlers(app)
    calls = []

    @app.post("/rooms/{room_id}/things")
    def route(room_id: str, actor: Actor = Depends(get_actor)):
        calls.append(room_id)
        return {"ok": True}

    response = TestClient(app).post("/rooms/does-not-exist/things")

    assert_rejected(response, "X-Device-Id header is required.")
    assert calls == []


# --- Opt-in per route --------------------------------------------------------


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"X-Device-Id": "", "X-Actor-Name": ""},
        {"X-Device-Id": "d" * 200, "X-Actor-Name": "%FF"},
        {"X-Device-Id": "   ", "X-Actor-Name": "%00"},
    ],
)
def test_route_without_the_dependency_ignores_missing_blank_and_malformed_headers(actor_client, headers):
    response = actor_client.post(OPEN_PATH, headers=headers)

    assert response.status_code == 200
    assert response.json() == {"ok": True}


# --- CORS preflight ----------------------------------------------------------


def test_preflight_to_an_actor_route_without_actor_headers_is_answered_by_cors():
    app = create_app()

    @app.post("/api/throwaway-actor")
    def route(actor: Actor = Depends(get_actor)):
        return actor

    response = TestClient(app).options(
        "/api/throwaway-actor",
        headers={
            "Origin": ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "x-device-id,x-actor-name",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ORIGIN
