import uuid
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app import timestamps
from app.main import app
from app.sql_store import SqlStore
from app.store import get_store

HEADERS = {"X-Device-Id": "device-1", "X-Actor-Name": "Tess"}


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


def room_id_of(store, name="Elm Street Allotment"):
    return next(room.id for room in store.list_rooms() if room.name == name)


def plant_id_of(store, common_name):
    return next(plant.id for plant in store.list_plants() if plant.common_name == common_name)


def live_room_plant(store, room_id=None):
    return store.list_room_plants(room_id or room_id_of(store))[0]


def add_payload(store, common_name="Tomato"):
    return {"plant_id": plant_id_of(store, common_name)}


def fill_room(store, room_id, live_count, *, deleted=0):
    """Make the room hold exactly ``live_count`` live plants plus ``deleted`` soft-deleted ones."""
    template = live_room_plant(store, room_id)
    for room_plant in store.list_room_plants(room_id, include_deleted=True):
        store.save_room_plant(room_plant.model_copy(update={"deleted_at": timestamps.now()}))
    for index in range(live_count + deleted):
        store.save_room_plant(
            template.model_copy(
                update={
                    "id": str(uuid.uuid4()),
                    "room_id": room_id,
                    "deleted_at": timestamps.now() if index >= live_count else None,
                }
            )
        )


# --- Add -------------------------------------------------------------------


def test_add_plant_returns_201_with_a_centred_unnamed_room_plant(api, store):
    room_id = room_id_of(store)
    payload = add_payload(store)

    response = api.post(f"/api/rooms/{room_id}/plants", json=payload, headers=HEADERS)

    body = response.json()
    assert response.status_code == 201
    assert str(uuid.UUID(body["id"], version=4)) == body["id"]
    assert body["room_id"] == room_id
    assert body["plant_id"] == payload["plant_id"]
    assert (body["x_pct"], body["y_pct"]) == (50, 50)
    assert body["nickname"] is None
    assert [body[f] for f in ("last_watered_at", "last_fed_at", "last_pruned_at", "last_harvested_at")] == [None] * 4
    assert body["added_by_name"] == "Tess"
    assert body["deleted_at"] is None


# --- Garden limit ------------------------------------------------------------


def test_add_plant_to_a_room_with_50_live_plants_returns_409_garden_full(api, store):
    room_id = room_id_of(store)
    fill_room(store, room_id, 50)

    response = api.post(f"/api/rooms/{room_id}/plants", json=add_payload(store), headers=HEADERS)

    assert response.status_code == 409
    assert response.json() == {"message": "This garden is full (50 plants max)"}


# --- Move ------------------------------------------------------------------


def test_move_plant_returns_200_with_the_updated_room_plant(api, store):
    original = live_room_plant(store)

    response = api.patch(f"/api/room-plants/{original.id}", json={"x_pct": 12, "y_pct": 34}, headers=HEADERS)

    body = response.json()
    assert response.status_code == 200
    assert (body["x_pct"], body["y_pct"]) == (12, 34)
    assert body["id"] == original.id
    assert store.get_room_plant(original.id).x_pct == 12


# --- Remove ----------------------------------------------------------------


def test_remove_plant_returns_204_sets_deleted_at_and_removing_again_returns_404_plant_gone(api, store):
    original = live_room_plant(store)

    response = api.delete(f"/api/room-plants/{original.id}", headers=HEADERS)

    assert response.status_code == 204
    assert response.content == b""
    assert store.get_room_plant(original.id).deleted_at is not None
    again = api.delete(f"/api/room-plants/{original.id}", headers=HEADERS)
    assert again.status_code == 404
    assert again.json() == {"message": "Plant is no longer in this garden"}


# --- Care ------------------------------------------------------------------


def tomato_in(store):
    """A live Tomato room plant (all four intervals set) in the Elm Street room."""
    room_id = room_id_of(store)
    tomato_id = plant_id_of(store, "Tomato")
    return next(rp for rp in store.list_room_plants(room_id) if rp.plant_id == tomato_id)


CARE_FIELDS = {
    "water": "last_watered_at",
    "feed": "last_fed_at",
    "prune": "last_pruned_at",
    "harvest": "last_harvested_at",
}


@pytest.mark.parametrize("care", ["water", "feed"])
def test_care_sets_only_the_matching_timestamp_and_returns_200(api, store, care):
    # Clear the seeded watering so "only the matching timestamp changed" is visible.
    tomato = tomato_in(store)
    store.save_room_plant(tomato.model_copy(update={"last_watered_at": None}))
    started = timestamps.now()

    response = api.post(f"/api/room-plants/{tomato.id}/care", json={"care": care}, headers=HEADERS)

    body = response.json()
    assert response.status_code == 200
    for name, field in CARE_FIELDS.items():
        if name == care:
            assert body[field] is not None
            assert store.get_room_plant(tomato.id).__dict__[field] >= started - timedelta(milliseconds=1)
        else:
            assert body[field] is None


# --- Feed events -------------------------------------------------------------


# --- Actor headers -----------------------------------------------------------


# --- Failures leave no trace; successes notify once ---------------------------


