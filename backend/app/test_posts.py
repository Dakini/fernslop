import uuid
from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app import live
from app.main import app
from app.sql_store import SqlStore
from app.store import get_store

HEADERS = {"X-Device-Id": "device-1", "X-Actor-Name": "Tess"}
MISSING_ID = "00000000-0000-4000-8000-000000000000"
JPEG = b"\xff\xd8\xff\xe0" + b"jpeg-body"
EMPTY_MESSAGE = "Write something or add a photo"
PHOTO_MESSAGE = "That photo didn't upload — try again"
LONG_MESSAGE = "Text must be at most 1000 characters"


@pytest.fixture
def store():
    """A fresh seeded store, injected in place of the configured store."""
    fresh = SqlStore("sqlite://")
    app.dependency_overrides[get_store] = lambda: fresh
    yield fresh
    app.dependency_overrides.pop(get_store, None)


@pytest.fixture
def api(store):
    return TestClient(app)


@pytest.fixture
def notify(monkeypatch, store):
    """Patch ``live.notify``; each call records whether a store transaction was open."""
    depth = {"open": 0}
    real_transaction = store.transaction

    @contextmanager
    def tracked():
        depth["open"] += 1
        try:
            with real_transaction():
                yield
        finally:
            depth["open"] -= 1

    store.transaction = tracked
    mock = MagicMock(side_effect=lambda room_id: mock.open_during_call.append(depth["open"]))
    mock.open_during_call = []
    monkeypatch.setattr(live, "notify", mock)
    return mock


def room_id_of(store):
    return store.list_rooms()[0].id


def post(api, room_id, body, headers=HEADERS):
    return api.post(f"/api/rooms/{room_id}/posts", json=body, headers=headers)


def upload_photo(api, data=JPEG):
    return api.post("/api/photos", files={"file": ("p.jpg", data, "image/jpeg")}).json()


# --- Success -------------------------------------------------------------------


def test_text_post_returns_201_and_a_post_event_with_trimmed_text(api, store):
    room_id = room_id_of(store)

    response = post(api, room_id, {"text": "  Hi  ", "photo_id": None})

    body = response.json()
    assert response.status_code == 201
    assert uuid.UUID(body["id"]).version == 4
    assert body["room_id"] == room_id
    assert body["type"] == "post"
    assert body["text"] == "Hi"
    assert body["photo_url"] is None
    assert body["room_plant_id"] is None
    assert body["undo_payload"] is None
    assert body["undone_at"] is None
    assert body["actor_name"] == "Tess"
    assert body["device_id"] == "device-1"


# --- Photos --------------------------------------------------------------------


def test_post_with_photo_copies_the_photos_url(api, store):
    photo = upload_photo(api)

    response = post(api, room_id_of(store), {"text": "Look", "photo_id": photo["id"]})

    assert response.status_code == 201
    assert response.json()["photo_url"] == photo["url"]


# --- Validation ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ({"text": "   \n ", "photo_id": None}, EMPTY_MESSAGE),
        ({"text": "a" * 1001, "photo_id": None}, LONG_MESSAGE),
        ({"text": 5, "photo_id": None}, "text must be a string"),
        ({"text": "Hi", "photo_id": MISSING_ID}, PHOTO_MESSAGE),
        # A right-to-left override can disguise what the line says (audit finding 3).
        ({"text": "Hi \u202egnp.exe", "photo_id": None}, "Text contains invalid characters"),
    ],
)
def test_invalid_post_is_400_with_message_and_writes_nothing(api, store, notify, body, message):
    room_id = room_id_of(store)
    feed_before = store.list_feed_events(room_id)
    activity_before = store.get_room(room_id).last_activity_at

    response = post(api, room_id, body)

    assert response.status_code == 400
    assert response.json()["message"] == message
    assert store.list_feed_events(room_id) == feed_before
    assert store.get_room(room_id).last_activity_at == activity_before
    notify.assert_not_called()


@pytest.mark.parametrize("room_id", [MISSING_ID])
def test_unknown_or_non_uuid_room_is_404(api, notify, room_id):
    response = post(api, room_id, {"text": "Hi", "photo_id": None})

    assert response.status_code == 404
    assert response.json() == {"message": "Room not found"}
    notify.assert_not_called()


# --- Actor headers ---------------------------------------------------------------


# --- Activity and notify -----------------------------------------------------------


def test_success_notifies_once_for_the_room_after_the_transaction_ends(api, store, notify):
    room_id = room_id_of(store)

    post(api, room_id, {"text": "Hi", "photo_id": None})

    notify.assert_called_once_with(room_id)
    assert notify.open_during_call == [0]


