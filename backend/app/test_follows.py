import re
import uuid

import pytest
from fastapi.testclient import TestClient

from app import live, timestamps
from app.main import app
from app.models import StoredFollow
from app.store import Store, get_store

PUBLIC_KEYS = {"id", "room_id", "email", "created_at"}
BAD_EMAIL = "That email doesn't look right"


@pytest.fixture
def store():
    """A fresh seeded store, injected in place of the module-level singleton."""
    fresh = Store()
    app.dependency_overrides[get_store] = lambda: fresh
    yield fresh
    app.dependency_overrides.pop(get_store, None)


@pytest.fixture
def follows_client(store):
    return TestClient(app)


def first_room(store):
    return store.list_rooms()[0]


def follow(client, room_id, email="ada@example.com"):
    return client.post(f"/api/rooms/{room_id}/follows", json={"email": email})


def unsubscribe(client, token):
    return client.post("/api/follows/unsubscribe", json={"token": token})


# --- Follow: first follow -----------------------------------------------------


def test_first_follow_returns_201_with_normalised_email_and_no_actor_headers(follows_client, store):
    room = first_room(store)

    response = follow(follows_client, room.id, "  Ada@Example.COM ")

    body = response.json()
    assert response.status_code == 201
    assert uuid.UUID(body["id"]).version == 4
    assert body["room_id"] == room.id
    assert body["email"] == "ada@example.com"
    assert body["created_at"] == timestamps.format_timestamp(store.get_follow_by_email(room.id, "ada@example.com").created_at)


def test_first_follow_created_at_comes_from_timestamps_now(follows_client, store, monkeypatch):
    room = first_room(store)
    fixed = timestamps.now().replace(year=2030)
    monkeypatch.setattr(timestamps, "now", lambda: fixed)

    response = follow(follows_client, room.id)

    assert response.json()["created_at"] == timestamps.format_timestamp(fixed)


def test_first_follow_stores_a_urlsafe_token_of_32_random_bytes(follows_client, store):
    room = first_room(store)

    follow(follows_client, room.id)

    token = store.get_follow_by_email(room.id, "ada@example.com").unsubscribe_token
    assert re.fullmatch(r"[A-Za-z0-9_-]{43}", token)


# --- Follow: token never leaks ------------------------------------------------


def test_follow_responses_never_contain_the_unsubscribe_token(follows_client, store):
    room = first_room(store)

    created = follow(follows_client, room.id)
    repeated = follow(follows_client, room.id, "ADA@example.com")

    token = store.get_follow_by_email(room.id, "ada@example.com").unsubscribe_token
    assert created.status_code == 201
    assert repeated.status_code == 200
    for response in (created, repeated):
        assert set(response.json()) == PUBLIC_KEYS
        assert token not in response.text


# --- Follow: repeat and other rooms ------------------------------------------


def test_following_again_with_same_email_in_any_case_returns_200_with_same_follow(follows_client, store):
    room = first_room(store)
    created = follow(follows_client, room.id, "ada@example.com").json()

    response = follow(follows_client, room.id, " ADA@Example.com")

    assert response.status_code == 200
    assert response.json() == created
    assert len(store.list_follows(room.id)) == 1


def test_same_email_on_a_different_room_is_a_separate_201(follows_client, store):
    room_a, room_b = store.list_rooms()[:2]
    first = follow(follows_client, room_a.id).json()

    response = follow(follows_client, room_b.id)

    assert response.status_code == 201
    assert response.json()["id"] != first["id"]
    assert response.json()["room_id"] == room_b.id


# --- Follow: validation -------------------------------------------------------


@pytest.mark.parametrize(
    "email",
    [
        "",
        "   ",
        "ada",
        "ada@example",
        "ada@@example.com",
        "a@b@example.com",
        "ada @example.com",
        "ada@exa mple.com",
        "@example.com",
        "ada@.com",
        "ada@example.",
        "ada@example..com",
        "a" * 243 + "@example.com",  # 255 characters
    ],
)
def test_follow_with_malformed_email_returns_400_and_stores_nothing(follows_client, store, email):
    room = first_room(store)

    response = follow(follows_client, room.id, email)

    assert response.status_code == 400
    assert response.json() == {"message": BAD_EMAIL}
    assert store.list_follows(room.id) == []


@pytest.mark.parametrize("body", [{}, {"email": None}, {"email": 5}, {"email": ["a@b.co"]}, {"email": {"a": 1}}])
def test_follow_with_missing_or_non_string_email_returns_400(follows_client, store, body):
    room = first_room(store)

    response = follows_client.post(f"/api/rooms/{room.id}/follows", json=body)

    assert response.status_code == 400
    assert response.json() == {"message": BAD_EMAIL}
    assert store.list_follows(room.id) == []


def test_follow_with_email_of_exactly_254_characters_is_accepted(follows_client, store):
    room = first_room(store)
    email = "a" * 242 + "@example.com"  # 254 characters

    response = follow(follows_client, room.id, email)

    assert len(email) == 254
    assert response.status_code == 201


def test_follow_with_invalid_json_returns_400_not_422(follows_client, store):
    room = first_room(store)

    response = follows_client.post(
        f"/api/rooms/{room.id}/follows", content=b"{nope", headers={"content-type": "application/json"}
    )

    assert response.status_code == 400
    assert "message" in response.json()


@pytest.mark.parametrize("payload", ["[]", '"ada@example.com"', "null", "5"])
def test_follow_with_non_object_body_returns_400_not_422(follows_client, store, payload):
    room = first_room(store)

    response = follows_client.post(
        f"/api/rooms/{room.id}/follows", content=payload, headers={"content-type": "application/json"}
    )

    assert response.status_code == 400
    assert "message" in response.json()


def test_follow_with_no_body_returns_400_not_422(follows_client, store):
    room = first_room(store)

    response = follows_client.post(f"/api/rooms/{room.id}/follows")

    assert response.status_code == 400


@pytest.mark.parametrize("room_id", ["nope", "5f1c8a44-2b0e-4f3a-9c55-0d3f3f0d9a11"])
def test_follow_on_unknown_room_returns_404(follows_client, room_id):
    response = follow(follows_client, room_id)

    assert response.status_code == 404
    assert response.json() == {"message": "Room not found"}


def test_follow_on_unknown_room_is_404_even_when_email_is_invalid(follows_client):
    response = follow(follows_client, "nope", "not an email")

    assert response.status_code == 404
    assert response.json() == {"message": "Room not found"}


def test_follow_on_unknown_room_is_404_even_when_body_is_not_json(follows_client):
    response = follows_client.post("/api/rooms/nope/follows", content=b"{nope")

    assert response.status_code == 404


# --- Unsubscribe --------------------------------------------------------------


def test_unsubscribe_with_stored_token_returns_true_and_removes_the_follow(follows_client, store):
    room = first_room(store)
    follow(follows_client, room.id)
    token = store.get_follow_by_email(room.id, "ada@example.com").unsubscribe_token

    response = unsubscribe(follows_client, token)

    assert response.status_code == 200
    assert response.json() == {"unsubscribed": True}
    assert store.list_follows(room.id) == []


def test_unsubscribe_repeated_returns_false(follows_client, store):
    room = first_room(store)
    follow(follows_client, room.id)
    token = store.get_follow_by_email(room.id, "ada@example.com").unsubscribe_token
    unsubscribe(follows_client, token)

    response = unsubscribe(follows_client, token)

    assert response.status_code == 200
    assert response.json() == {"unsubscribed": False}


@pytest.mark.parametrize("token", ["", "not-a-real-token"])
def test_unsubscribe_with_unknown_or_empty_token_returns_false_and_keeps_follows(follows_client, store, token):
    room = first_room(store)
    follow(follows_client, room.id)

    response = unsubscribe(follows_client, token)

    assert response.status_code == 200
    assert response.json() == {"unsubscribed": False}
    assert len(store.list_follows(room.id)) == 1


def test_unsubscribe_empty_token_does_not_remove_a_follow_stored_with_an_empty_token(follows_client, store):
    room = first_room(store)
    store.save_follow(
        StoredFollow(
            id=str(uuid.uuid4()),
            room_id=room.id,
            email="x@example.com",
            created_at=timestamps.now(),
            unsubscribe_token="",
        )
    )

    response = unsubscribe(follows_client, "")

    assert response.json() == {"unsubscribed": False}
    assert len(store.list_follows(room.id)) == 1


@pytest.mark.parametrize("body", [{}, {"token": None}, {"token": 5}, {"token": ["x"]}, {"other": "x"}])
def test_unsubscribe_with_missing_or_non_string_token_returns_400(follows_client, body):
    response = follows_client.post("/api/follows/unsubscribe", json=body)

    assert response.status_code == 400
    assert "message" in response.json()


@pytest.mark.parametrize("payload", [b"{nope", b"[]", b""])
def test_unsubscribe_with_invalid_json_or_non_object_body_returns_400(follows_client, payload):
    response = follows_client.post(
        "/api/follows/unsubscribe", content=payload, headers={"content-type": "application/json"}
    )

    assert response.status_code == 400


def test_unsubscribe_only_removes_the_follow_with_that_token(follows_client, store):
    room_a, room_b = store.list_rooms()[:2]
    follow(follows_client, room_a.id)
    follow(follows_client, room_b.id)
    token = store.get_follow_by_email(room_a.id, "ada@example.com").unsubscribe_token

    unsubscribe(follows_client, token)

    assert store.list_follows(room_a.id) == []
    assert len(store.list_follows(room_b.id)) == 1


def test_following_again_after_unsubscribing_returns_201_with_new_id_and_token(follows_client, store):
    room = first_room(store)
    old_id = follow(follows_client, room.id).json()["id"]
    old_token = store.get_follow_by_email(room.id, "ada@example.com").unsubscribe_token
    unsubscribe(follows_client, old_token)

    response = follow(follows_client, room.id)

    new = store.get_follow_by_email(room.id, "ada@example.com")
    assert response.status_code == 201
    assert response.json()["id"] != old_id
    assert new.unsubscribe_token != old_token


# --- No side effects ----------------------------------------------------------


def test_follow_and_unsubscribe_do_not_touch_room_feed_or_live_stream(follows_client, store, monkeypatch):
    room = first_room(store)
    feed_before = store.list_feed_events(room.id)
    notified = []
    monkeypatch.setattr(live, "notify", lambda *args, **kwargs: notified.append(args))

    follow(follows_client, room.id)
    follow(follows_client, room.id)
    token = store.get_follow_by_email(room.id, "ada@example.com").unsubscribe_token
    unsubscribe(follows_client, token)

    assert store.get_room(room.id) == room
    assert store.list_feed_events(room.id) == feed_before
    assert notified == []
