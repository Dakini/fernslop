import uuid
from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app import live
from app.main import app
from app.store import Store, get_store

HEADERS = {"X-Device-Id": "device-1", "X-Actor-Name": "Tess"}
MISSING_ID = "00000000-0000-4000-8000-000000000000"
JPEG = b"\xff\xd8\xff\xe0" + b"jpeg-body"
EMPTY_MESSAGE = "Write something or add a photo"
PHOTO_MESSAGE = "That photo didn't upload — try again"
LONG_MESSAGE = "Text must be at most 1000 characters"


@pytest.fixture
def store():
    """A fresh seeded store, injected in place of the module-level singleton."""
    fresh = Store()
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


def test_post_is_first_in_the_room_feed(api, store):
    room_id = room_id_of(store)

    event = post(api, room_id, {"text": "Hi", "photo_id": None}).json()

    feed = api.get(f"/api/rooms/{room_id}").json()["feed"]
    assert feed[0] == event


def test_missing_text_or_photo_id_counts_as_empty(api, store):
    room_id = room_id_of(store)
    photo = upload_photo(api)

    only_photo = post(api, room_id, {"photo_id": photo["id"]})
    only_text = post(api, room_id, {"text": "Hello"})

    assert only_photo.status_code == 201
    assert only_photo.json()["text"] == ""
    assert only_text.status_code == 201
    assert only_text.json()["photo_url"] is None


def test_extra_fields_such_as_photo_url_are_ignored(api, store):
    response = post(api, room_id_of(store), {"text": "Hi", "photo_id": None, "photo_url": "http://evil", "type": "plant_added"})

    assert response.status_code == 201
    assert response.json()["photo_url"] is None
    assert response.json()["type"] == "post"


def test_text_of_exactly_1000_characters_after_trimming_is_accepted(api, store):
    response = post(api, room_id_of(store), {"text": " " + "a" * 1000 + " ", "photo_id": None})

    assert response.status_code == 201
    assert response.json()["text"] == "a" * 1000


# --- Photos --------------------------------------------------------------------


def test_post_with_photo_copies_the_photos_url(api, store):
    photo = upload_photo(api)

    response = post(api, room_id_of(store), {"text": "Look", "photo_id": photo["id"]})

    assert response.status_code == 201
    assert response.json()["photo_url"] == photo["url"]


def test_photo_without_text_is_valid_with_empty_text(api, store):
    photo = upload_photo(api)

    response = post(api, room_id_of(store), {"text": "   ", "photo_id": photo["id"]})

    assert response.status_code == 201
    assert response.json()["text"] == ""


def test_post_reads_back_the_bytes_of_the_photo_it_just_uploaded(api, store):
    photo = upload_photo(api, JPEG + b"unique-bytes")
    room_id = room_id_of(store)
    post(api, room_id, {"text": "", "photo_id": photo["id"]})

    photo_url = api.get(f"/api/rooms/{room_id}").json()["feed"][0]["photo_url"]
    served = api.get(photo_url)

    assert served.status_code == 200
    assert served.content == JPEG + b"unique-bytes"


def test_one_photo_can_be_posted_several_times_and_to_several_rooms(api, store):
    photo = upload_photo(api)
    first_room, second_room = [room.id for room in store.list_rooms()[:2]]

    responses = [
        post(api, first_room, {"text": "", "photo_id": photo["id"]}),
        post(api, first_room, {"text": "", "photo_id": photo["id"]}),
        post(api, second_room, {"text": "", "photo_id": photo["id"]}),
    ]

    assert [response.status_code for response in responses] == [201, 201, 201]
    assert {response.json()["photo_url"] for response in responses} == {photo["url"]}


# --- Validation ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ({"text": "", "photo_id": None}, EMPTY_MESSAGE),
        ({"text": "   \n ", "photo_id": None}, EMPTY_MESSAGE),
        ({}, EMPTY_MESSAGE),
        ({"text": "a" * 1001, "photo_id": None}, LONG_MESSAGE),
        ({"text": " " + "a" * 1001 + " ", "photo_id": None}, LONG_MESSAGE),
        ({"text": 5, "photo_id": None}, "text must be a string"),
        ({"text": ["x"], "photo_id": None}, "text must be a string"),
        ({"text": None, "photo_id": None}, "text must be a string"),
        ({"text": "Hi", "photo_id": MISSING_ID}, PHOTO_MESSAGE),
        ({"text": "Hi", "photo_id": "not-a-uuid"}, PHOTO_MESSAGE),
        ({"text": "Hi", "photo_id": ""}, PHOTO_MESSAGE),
        ({"text": "Hi", "photo_id": 5}, PHOTO_MESSAGE),
        ({"text": "Hi", "photo_id": True}, PHOTO_MESSAGE),
        ({"text": "", "photo_id": MISSING_ID}, PHOTO_MESSAGE),
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


@pytest.mark.parametrize("raw", [b"{not json", b"", b"[]", b'"text"', b"5", b"null", b"\xff\xfe"])
def test_invalid_json_or_non_object_body_is_400_never_422(api, store, notify, raw):
    room_id = room_id_of(store)
    feed_before = store.list_feed_events(room_id)

    response = api.post(
        f"/api/rooms/{room_id}/posts", content=raw, headers={**HEADERS, "Content-Type": "application/json"}
    )

    assert response.status_code == 400
    assert "message" in response.json()
    assert store.list_feed_events(room_id) == feed_before
    notify.assert_not_called()


@pytest.mark.parametrize("room_id", [MISSING_ID, "not-a-uuid"])
def test_unknown_or_non_uuid_room_is_404(api, notify, room_id):
    response = post(api, room_id, {"text": "Hi", "photo_id": None})

    assert response.status_code == 404
    assert response.json() == {"message": "Room not found"}
    notify.assert_not_called()


# --- Actor headers ---------------------------------------------------------------


@pytest.mark.parametrize(
    "headers",
    [{}, {"X-Device-Id": "device-1"}, {"X-Actor-Name": "Tess"}, {"X-Device-Id": " ", "X-Actor-Name": "Tess"}],
)
def test_post_without_valid_actor_headers_is_400_and_writes_nothing(api, store, notify, headers):
    room_id = room_id_of(store)
    feed_before = store.list_feed_events(room_id)

    response = post(api, room_id, {"text": "Hi", "photo_id": None}, headers=headers)

    assert response.status_code == 400
    assert store.list_feed_events(room_id) == feed_before
    notify.assert_not_called()


# --- Activity and notify -----------------------------------------------------------


def test_success_sets_last_activity_to_the_events_created_at(api, store):
    room_id = room_id_of(store)

    event = post(api, room_id, {"text": "Hi", "photo_id": None}).json()

    stored = store.list_feed_events(room_id)[0]
    assert store.get_room(room_id).last_activity_at == stored.created_at
    assert event["created_at"] == api.get(f"/api/rooms/{room_id}").json()["room"]["last_activity_at"]


def test_success_notifies_once_for_the_room_after_the_transaction_ends(api, store, notify):
    room_id = room_id_of(store)

    post(api, room_id, {"text": "Hi", "photo_id": None})

    notify.assert_called_once_with(room_id)
    assert notify.open_during_call == [0]


def test_success_writes_exactly_one_feed_event(api, store):
    room_id = room_id_of(store)
    before = len(store.list_feed_events(room_id))

    post(api, room_id, {"text": "Hi", "photo_id": None})

    assert len(store.list_feed_events(room_id)) == before + 1
