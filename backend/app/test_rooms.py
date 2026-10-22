import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from app.body import MAX_JSON_BODY_BYTES
from app.main import app
from app.models import Room
from app.sql_store import SqlStore
from app.store import get_store

SEED_ROOM_NAMES = ["Elm Street Allotment", "Balcony Jungle", "Orchard Corner"]


@pytest.fixture
def store():
    """A fresh seeded store, injected in place of the configured store."""
    fresh = SqlStore("sqlite://")
    app.dependency_overrides[get_store] = lambda: fresh
    yield fresh
    app.dependency_overrides.pop(get_store, None)


@pytest.fixture
def rooms_client(store):
    return TestClient(app)


def seed_room_id(store, name):
    return next(room.id for room in store.list_rooms() if room.name == name)


# --- List ------------------------------------------------------------------


def test_list_rooms_on_seed_returns_three_summaries_newest_activity_first(rooms_client):
    response = rooms_client.get("/api/rooms")

    assert response.status_code == 200
    assert [summary["room"]["name"] for summary in response.json()["rooms"]] == SEED_ROOM_NAMES
    assert response.json()["next"] is None


def add_rooms(store, count):
    """``count`` rooms whose activity is older than the seed's, the first one most recent."""
    start = datetime(2020, 1, 1, tzinfo=UTC)
    for i in range(count):
        at = start - timedelta(minutes=i)
        store.save_room(Room(id=str(uuid.uuid4()), name=f"Plot {i}", description="", region="", created_at=at, last_activity_at=at))


def count_queries(store, request):
    statements = []
    listen = lambda *args: statements.append(args[2])
    event.listen(store._engine, "before_cursor_execute", listen)
    try:
        request()
    finally:
        event.remove(store._engine, "before_cursor_execute", listen)
    return len(statements)


def test_list_rooms_runs_as_many_queries_for_200_rooms_as_for_3(rooms_client, store):
    few = count_queries(store, lambda: rooms_client.get("/api/rooms?limit=100"))
    add_rooms(store, 197)

    many = count_queries(store, lambda: rooms_client.get("/api/rooms?limit=100"))

    assert many == few > 0


def test_list_rooms_pages_through_every_live_room_once_skipping_deleted_ones(rooms_client, store):
    add_rooms(store, 4)
    deleted = seed_room_id(store, "Balcony Jungle")
    rooms_client.delete(f"/api/rooms/{deleted}")
    pages, before = [], None

    while True:
        body = rooms_client.get("/api/rooms", params={"limit": 2, **({"before": before} if before else {})}).json()
        pages.append([summary["room"]["name"] for summary in body["rooms"]])
        before = body["next"]
        if before is None:
            break

    assert pages == [
        ["Elm Street Allotment", "Orchard Corner"],
        ["Plot 0", "Plot 1"],
        ["Plot 2", "Plot 3"],
    ]


@pytest.mark.parametrize("query", ["limit=0", "limit=101", "limit=ten", "before=nonsense"])
def test_list_rooms_with_a_bad_limit_or_cursor_gives_400(rooms_client, query):
    response = rooms_client.get(f"/api/rooms?{query}")

    assert response.status_code == 400


# --- Create ----------------------------------------------------------------


def test_create_room_trims_fields_and_returns_201_room(rooms_client):
    response = rooms_client.post("/api/rooms", json={"name": "  Back Yard  ", "description": " Sunny "})

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"id", "name", "description", "region", "created_at", "last_activity_at"}
    assert body["name"] == "Back Yard"
    assert body["description"] == "Sunny"
    assert body["region"] == ""


# --- Create: validation ----------------------------------------------------


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"name": 5},
        {"name": "   "},
    ],
)
def test_create_room_with_missing_non_string_or_blank_name_gives_400(rooms_client, store, body):
    response = rooms_client.post("/api/rooms", json=body)

    assert response.status_code == 400
    assert response.json() == {"message": "A room needs a name"}
    assert len(store.list_rooms()) == 3


# --- Get state -------------------------------------------------------------


def test_get_room_state_returns_room_live_plants_areas_and_feed(rooms_client, store):
    elm = seed_room_id(store, "Elm Street Allotment")

    response = rooms_client.get(f"/api/rooms/{elm}")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"room", "plants", "areas", "feed"}
    assert body["room"]["id"] == elm
    assert body["room"]["name"] == "Elm Street Allotment"
    assert len(body["plants"]) == 4
    assert len(body["areas"]) == 2
    assert all(item["deleted_at"] is None for item in body["plants"] + body["areas"])


@pytest.mark.parametrize("room_id", ["not-a-uuid-at-all", str(uuid.uuid4())])
def test_get_room_state_for_unknown_id_gives_404_not_422(rooms_client, room_id):
    response = rooms_client.get(f"/api/rooms/{room_id}")

    assert response.status_code == 404
    assert response.json() == {"message": "Room not found"}




def test_create_room_with_a_line_break_in_the_name_gives_400_and_creates_nothing(rooms_client, store):
    # A CRLF in the name would end up in the digest email's Subject header (audit finding 3).
    response = rooms_client.post("/api/rooms", json={"name": "Subject\r\nBcc: everyone@example.com"})

    assert response.status_code == 400
    assert response.json() == {"message": "Name contains invalid characters"}
    assert len(store.list_rooms()) == 3


# --- Request bodies (audit findings 4 and 9) ---------------------------------


def test_create_room_sent_as_text_plain_gives_415_and_creates_nothing(rooms_client, store):
    # text/plain is a CORS "simple" request, so another site could send it without a preflight.
    response = rooms_client.post("/api/rooms", content=b'{"name": "Sneaky"}', headers={"Content-Type": "text/plain"})

    assert response.status_code == 415
    assert "Sneaky" not in [room.name for room in store.list_rooms()]


def test_create_room_with_a_body_over_the_size_cap_gives_413_and_creates_nothing(rooms_client, store):
    rooms_before = store.list_rooms()

    response = rooms_client.post("/api/rooms", json={"name": "Big", "description": "x" * (MAX_JSON_BODY_BYTES + 1)})

    assert response.status_code == 413
    assert store.list_rooms() == rooms_before


def test_create_room_with_a_chunked_body_over_the_size_cap_gives_413_and_creates_nothing(rooms_client, store):
    # A generator body is sent chunked with no Content-Length, so only the streaming check can catch it.
    rooms_before = store.list_rooms()
    chunks = (b"x" * 1024 for _ in range(MAX_JSON_BODY_BYTES // 1024 + 1))

    response = rooms_client.post("/api/rooms", content=chunks, headers={"Content-Type": "application/json"})

    assert response.status_code == 413
    assert response.json() == {"message": "Request body is too large"}
    assert store.list_rooms() == rooms_before


def test_create_room_sent_as_json_with_a_charset_gives_201(rooms_client):
    response = rooms_client.post(
        "/api/rooms", content=b'{"name": "Charset"}', headers={"Content-Type": "application/json; charset=utf-8"}
    )

    assert response.status_code == 201
    assert response.json()["name"] == "Charset"
