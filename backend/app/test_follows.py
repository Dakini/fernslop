from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app import timestamps
from app.digest import InMemorySender, get_email_sender
from app.main import app
from app.sql_store import SqlStore
from app.store import get_store

BAD_EMAIL = "That email doesn't look right"


@pytest.fixture
def store():
    """A fresh seeded store, injected in place of the configured store."""
    fresh = SqlStore("sqlite://")
    app.dependency_overrides[get_store] = lambda: fresh
    yield fresh
    app.dependency_overrides.pop(get_store, None)


@pytest.fixture
def sender():
    """Records the emails a request sends, in place of the console sender."""
    recorder = InMemorySender()
    app.dependency_overrides[get_email_sender] = lambda: recorder
    yield recorder
    app.dependency_overrides.pop(get_email_sender, None)


@pytest.fixture
def follows_client(store, sender):
    return TestClient(app)


def first_room(store):
    return store.list_rooms()[0]


def follow(client, room_id, email="ada@example.com"):
    return client.post(f"/api/rooms/{room_id}/follows", json={"email": email})


def unsubscribe(client, token):
    return client.post("/api/follows/unsubscribe", json={"token": token})


def confirm(client, token):
    return client.post("/api/follows/confirm", json={"token": token})


# --- Follow: double opt-in ----------------------------------------------------


def test_follow_answers_201_with_only_room_and_email_and_emails_a_confirm_link_until_confirmed(
    follows_client, store, sender
):
    room = first_room(store)

    created = follow(follows_client, room.id, "  Ada@Example.COM ")
    repeated = follow(follows_client, room.id, "ADA@example.com")
    stored = store.get_follow_by_email(room.id, "ada@example.com")
    confirmed = confirm(follows_client, stored.unsubscribe_token)
    after_confirm = follow(follows_client, room.id, "ada@example.com")

    # The same answer every time, so it never reveals an earlier follow, and never the token.
    for response in (created, repeated, after_confirm):
        assert response.status_code == 201
        assert response.json() == {"room_id": room.id, "email": "ada@example.com"}
    assert len(store.list_follows(room.id)) == 1
    # One email per unconfirmed request, none once confirmed; the token is only in the fragment.
    link = f"http://localhost:5173/confirm-follow#token={stored.unsubscribe_token}"
    assert [(to, link in body) for to, _, body in sender.sent] == [("ada@example.com", True)] * 2
    assert confirmed.json() == {"confirmed": True}
    assert confirm(follows_client, stored.unsubscribe_token).json() == {"confirmed": True}
    assert store.get_follow_by_email(room.id, "ada@example.com").confirmed_at is not None


def test_confirm_with_an_unknown_token_or_after_7_days_returns_false_and_changes_nothing(follows_client, store):
    room = first_room(store)
    follow(follows_client, room.id)
    stale = store.get_follow_by_email(room.id, "ada@example.com")
    stale = stale.model_copy(update={"created_at": timestamps.now() - timedelta(days=7, minutes=1)})
    store.save_follow(stale)

    unknown = confirm(follows_client, "no-such-token")
    expired = confirm(follows_client, stale.unsubscribe_token)

    assert unknown.json() == {"confirmed": False}
    assert expired.json() == {"confirmed": False}
    assert store.get_follow_by_email(room.id, "ada@example.com").confirmed_at is None


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


