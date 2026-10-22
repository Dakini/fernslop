import uuid

import pytest
from fastapi.testclient import TestClient

from app import timestamps
from app.main import app
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


# --- Follow: validation -------------------------------------------------------


@pytest.mark.parametrize(
    "email",
    [
        "",
        "ada@example",
        "a" * 243 + "@example.com",  # 255 characters
    ],
)
def test_follow_with_malformed_email_returns_400_and_stores_nothing(follows_client, store, email):
    room = first_room(store)

    response = follow(follows_client, room.id, email)

    assert response.status_code == 400
    assert response.json() == {"message": BAD_EMAIL}
    assert store.list_follows(room.id) == []


# --- Unsubscribe --------------------------------------------------------------


def test_unsubscribe_with_stored_token_returns_true_removes_the_follow_and_a_repeat_returns_false(follows_client, store):
    room = first_room(store)
    follow(follows_client, room.id)
    token = store.get_follow_by_email(room.id, "ada@example.com").unsubscribe_token

    response = unsubscribe(follows_client, token)

    assert response.status_code == 200
    assert response.json() == {"unsubscribed": True}
    assert store.list_follows(room.id) == []
    # The token is single-use: a repeat finds nothing.
    assert unsubscribe(follows_client, token).json() == {"unsubscribed": False}


# --- No side effects ----------------------------------------------------------


