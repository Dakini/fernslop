import io
import uuid
from contextlib import contextmanager
from datetime import timedelta
from unittest.mock import MagicMock
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import event

from app import live, timestamps
from app.main import app
from app.models import FeedEvent, Room
from app.seed import seed_id
from app.sql_store import SqlStore
from app.store import get_store

HEADERS = {"X-Device-Id": "device-1", "X-Actor-Name": "Tess"}
MISSING_ID = "00000000-0000-4000-8000-000000000000"
SEED_PHOTO_ID = seed_id("photo:elm-street-harvest")


def make_jpeg():
    out = io.BytesIO()
    Image.new("RGB", (2, 2), "green").save(out, "JPEG")
    return out.getvalue()


JPEG = make_jpeg()
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


# The ZWJ in 👩‍🌾 is a format character (Cf), but the text filter must let it through (#193).
@pytest.mark.parametrize("value", ["👩‍🌾", "👍🏽", "🇬🇧", "Zoë", "Аня 花子"])
def test_post_accepts_emoji_and_non_latin_letters_in_name_and_text(api, store, value):
    headers = {**HEADERS, "X-Actor-Name": quote(value)}

    response = post(api, room_id_of(store), {"text": value, "photo_id": None}, headers=headers)

    assert response.status_code == 201
    assert (response.json()["actor_name"], response.json()["text"]) == (value, value)


# --- Photos --------------------------------------------------------------------


def test_post_with_photo_copies_the_photos_url(api, store):
    photo = upload_photo(api)

    response = post(api, room_id_of(store), {"text": "Look", "photo_id": photo["id"]})

    assert response.status_code == 201
    assert response.json()["photo_url"] == photo["url"]


def count_queries(store, request):
    statements = []
    listen = lambda *args: statements.append(args[2])
    event.listen(store._engine, "before_cursor_execute", listen)
    try:
        response = request()
    finally:
        event.remove(store._engine, "before_cursor_execute", listen)
    return response, len(statements)


def add_room_with_post(store, photo_url=None, *, undone=False):
    """A room with one post; returns the room id."""
    now = timestamps.now()
    room = Room(id=str(uuid.uuid4()), name="Plot", description="", region="", created_at=now, last_activity_at=now)
    store.save_room(room)
    store.save_feed_event(
        FeedEvent(
            id=str(uuid.uuid4()),
            room_id=room.id,
            type="post",
            actor_name="Ann",
            device_id="device-2",
            room_plant_id=None,
            text="Old",
            photo_url=photo_url,
            undo_payload=None,
            undone_at=now if undone else None,
            created_at=now,
        )
    )
    return room.id


# The photo-in-use check is one lookup by URL, not a read of every feed (#213).
def test_photo_post_runs_as_many_queries_for_200_rooms_as_for_3(api, store):
    room_id = room_id_of(store)
    first, second = upload_photo(api), upload_photo(api)
    few_response, few = count_queries(store, lambda: post(api, room_id, {"text": "", "photo_id": first["id"]}))
    for _ in range(197):
        add_room_with_post(store)

    many_response, many = count_queries(store, lambda: post(api, room_id, {"text": "", "photo_id": second["id"]}))

    assert (few_response.status_code, many_response.status_code) == (201, 201)
    assert many == few > 0


# --- Validation ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ({"text": "   \n ", "photo_id": None}, EMPTY_MESSAGE),
        ({"text": "a" * 1001, "photo_id": None}, LONG_MESSAGE),
        ({"text": 5, "photo_id": None}, "text must be a string"),
        ({"text": "Hi", "photo_id": MISSING_ID}, PHOTO_MESSAGE),
        # The seed post already shows this photo; any post using a photo blocks reuse (audit finding 14).
        ({"text": "Hi", "photo_id": SEED_PHOTO_ID}, "That photo is already in a post"),
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


@pytest.mark.parametrize("where", ["other room", "undone post", "deleted room"])
def test_photo_already_in_any_post_is_400_and_writes_nothing(api, store, notify, where):
    photo = upload_photo(api)
    other_id = add_room_with_post(store, photo["url"], undone=where == "undone post")
    if where == "deleted room":
        store.delete_room(other_id, timestamps.now())  # soft-deleted, not yet purged (#196)
    room_id = room_id_of(store)
    feed_before = store.list_feed_events(room_id)

    response = post(api, room_id, {"text": "Mine", "photo_id": photo["id"]})

    assert response.status_code == 400
    assert response.json()["message"] == "That photo is already in a post"
    assert store.list_feed_events(room_id) == feed_before
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


# --- Daily post cap (#210) -------------------------------------------------------


def make_post(room_id, created_at, **overrides):
    fields = {
        "id": str(uuid.uuid4()),
        "room_id": room_id,
        "type": "post",
        "actor_name": "Ann",
        "device_id": "device-2",
        "room_plant_id": None,
        "text": "Hello",
        "photo_url": None,
        "undo_payload": None,
        "undone_at": None,
        "created_at": created_at,
    }
    return FeedEvent(**{**fields, **overrides})


def test_201st_post_in_a_room_within_24_hours_gives_429_and_writes_nothing(api, store, notify):
    now = timestamps.now()
    room = Room(id=str(uuid.uuid4()), name="Busy", description="", region="", created_at=now, last_activity_at=now)
    store.save_room(room)
    store.save_feed_event(make_post(room.id, now - timedelta(hours=23), undone_at=now))  # undone posts count
    for _ in range(198):
        store.save_feed_event(make_post(room.id, now - timedelta(minutes=1)))
    store.save_feed_event(make_post(room.id, now - timedelta(hours=25)))  # outside the window
    store.save_feed_event(make_post(room.id, now, type="care_done"))  # not a post
    assert post(api, room.id, {"text": "200th"}).status_code == 201
    feed_before = store.list_feed_events(room.id)

    response = post(api, room.id, {"text": "201st"})

    assert response.status_code == 429
    retry_after = int(response.headers["Retry-After"])
    assert 3500 < retry_after <= 3600  # until the oldest post in the window is 24 hours old
    assert response.json() == {"message": f"You're going a bit fast. Try again in {retry_after} seconds."}
    assert store.list_feed_events(room.id) == feed_before
    notify.assert_called_once()  # only for the 200th


# --- Daily photo post cap (#222) -------------------------------------------------


def make_busy_room(store, now):
    room = Room(id=str(uuid.uuid4()), name="Snappy", description="", region="", created_at=now, last_activity_at=now)
    store.save_room(room)
    return room


def test_photo_post_past_the_daily_photo_cap_gives_429_and_writes_nothing(api, store, notify, monkeypatch):
    monkeypatch.setenv("FERNSLOP_PHOTO_POSTS_PER_DAY", "2")
    monkeypatch.setenv("FERNSLOP_RATE_LIMIT", "off")  # does not turn this cap off
    now = timestamps.now()
    room = make_busy_room(store, now)
    store.save_feed_event(make_post(room.id, now - timedelta(hours=23), photo_url="/p/a.jpg", undone_at=now))
    store.save_feed_event(make_post(room.id, now - timedelta(hours=25), photo_url="/p/old.jpg"))  # outside window
    store.save_feed_event(make_post(room.id, now - timedelta(minutes=1)))  # text-only does not count
    assert post(api, room.id, {"photo_id": upload_photo(api)["id"]}).status_code == 201
    photo_id = upload_photo(api)["id"]
    feed_before = store.list_feed_events(room.id)

    response = post(api, room.id, {"photo_id": photo_id})

    assert response.status_code == 429
    retry_after = int(response.headers["Retry-After"])
    assert 3500 < retry_after <= 3600  # until the undone photo post is 24 hours old
    assert response.json() == {"message": f"You're going a bit fast. Try again in {retry_after} seconds."}
    assert store.list_feed_events(room.id) == feed_before
    assert not store.photo_url_in_feed(store.get_photo(photo_id).url)  # left for the 6-hour cleanup
    notify.assert_called_once()  # only for the first photo post


def test_text_post_in_a_room_at_the_default_photo_cap_still_gives_201(api, store):
    now = timestamps.now()
    room = make_busy_room(store, now)
    for i in range(15):
        store.save_feed_event(make_post(room.id, now - timedelta(minutes=1), photo_url=f"/p/{i}.jpg"))
    assert post(api, room.id, {"photo_id": upload_photo(api)["id"]}).status_code == 429

    response = post(api, room.id, {"text": "Still growing"})

    assert response.status_code == 201


