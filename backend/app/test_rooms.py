import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.store import Store, get_store

SEED_ROOM_NAMES = ["Elm Street Allotment", "Balcony Jungle", "Orchard Corner"]


@pytest.fixture
def store():
    """A fresh seeded store, injected in place of the module-level singleton."""
    fresh = Store()
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
    assert [summary["room"]["name"] for summary in response.json()] == SEED_ROOM_NAMES


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


