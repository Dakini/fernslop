import uuid
from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app import live, timestamps
from app.main import app
from app.sql_store import SqlStore
from app.store import get_store

HEADERS = {"X-Device-Id": "device-1", "X-Actor-Name": "Tess"}
UNDO_HEADERS = {"X-Device-Id": "device-2", "X-Actor-Name": "Uma"}


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


def room_id_of(store, name="Elm Street Allotment"):
    return next(room.id for room in store.list_rooms() if room.name == name)


def plant_id_of(store, common_name):
    return next(plant.id for plant in store.list_plants() if plant.common_name == common_name)


def tomato_in(store):
    """A live Tomato room plant (all four intervals set) in the Elm Street room."""
    tomato_id = plant_id_of(store, "Tomato")
    return next(rp for rp in store.list_room_plants(room_id_of(store)) if rp.plant_id == tomato_id)


def fill_plants(store, room_id, live_count):
    """Make the room hold exactly ``live_count`` live plants; the earlier ones become soft-deleted."""
    template = store.list_room_plants(room_id, include_deleted=True)[0].model_copy(update={"deleted_at": None})
    for room_plant in store.list_room_plants(room_id):
        store.save_room_plant(room_plant.model_copy(update={"deleted_at": timestamps.now()}))
    for _ in range(live_count):
        store.save_room_plant(template.model_copy(update={"id": str(uuid.uuid4()), "deleted_at": None}))


def snapshot(store, room_id):
    return (
        store.list_room_plants(room_id, include_deleted=True),
        store.list_areas(room_id, include_deleted=True),
        store.list_feed_events(room_id),
        store.get_room(room_id).last_activity_at,
    )


def newest_event(store, room_id):
    return store.list_feed_events(room_id)[0]


def undo(api, event_id, headers=UNDO_HEADERS):
    return api.post(f"/api/feed-events/{event_id}/undo", headers=headers)


def move(api, room_plant_id, x, y):
    return api.patch(f"/api/room-plants/{room_plant_id}", json={"x_pct": x, "y_pct": y}, headers=HEADERS)


def remove_plant(api, store):
    """Remove the Elm Street tomato through the API; return (plant before, undo event)."""
    before = tomato_in(store)
    api.delete(f"/api/room-plants/{before.id}", headers=HEADERS)
    return before, newest_event(store, before.room_id)


# --- Success -----------------------------------------------------------------


def test_undo_returns_204_with_an_empty_body_and_sets_undone_at(api, store):
    plant = tomato_in(store)
    move(api, plant.id, 70, 80)
    event = newest_event(store, plant.room_id)

    response = undo(api, event.id)

    stored = store.get_feed_event(event.id)
    assert response.status_code == 204
    assert response.content == b""
    assert stored.undone_at is not None
    assert stored.undone_at >= event.created_at


# --- restore_plant -----------------------------------------------------------


def test_undo_of_a_removed_plant_brings_it_back_into_the_room_state(api, store):
    before, event = remove_plant(api, store)

    response = undo(api, event.id)

    plants = api.get(f"/api/rooms/{before.room_id}").json()["plants"]
    restored = next(p for p in plants if p["id"] == before.id)
    assert response.status_code == 204
    assert restored["deleted_at"] is None
    assert store.get_room_plant(before.id) == before


# --- delete_plant ------------------------------------------------------------


def test_undo_of_an_added_plant_soft_deletes_it(api, store):
    room_id = room_id_of(store)
    added = api.post(
        f"/api/rooms/{room_id}/plants", json={"plant_id": plant_id_of(store, "Tomato")}, headers=HEADERS
    ).json()

    response = undo(api, newest_event(store, room_id).id)

    plants = api.get(f"/api/rooms/{room_id}").json()["plants"]
    assert response.status_code == 204
    assert added["id"] not in [p["id"] for p in plants]
    assert store.get_room_plant(added["id"]).deleted_at is not None


# --- Areas -------------------------------------------------------------------


# --- Cannot undo / already undone --------------------------------------------


def test_undo_twice_returns_409_already_undone_and_changes_nothing_the_second_time(api, store, notify):
    plant = tomato_in(store)
    move(api, plant.id, 70, 80)
    event = newest_event(store, plant.room_id)
    undo(api, event.id)
    # A later edit that undoing the event again would wrongly overwrite.
    move(api, plant.id, 1, 2)
    before = snapshot(store, plant.room_id)
    undone_at = store.get_feed_event(event.id).undone_at
    notify.reset_mock()

    response = undo(api, event.id)

    assert response.status_code == 409
    assert response.json() == {"message": "Already undone"}
    assert snapshot(store, plant.room_id) == before
    assert store.get_feed_event(event.id).undone_at == undone_at
    notify.assert_not_called()


# --- Later changes -----------------------------------------------------------


def test_undo_of_a_move_after_a_later_watering_returns_409_until_the_watering_is_undone(api, store, notify):
    plant = tomato_in(store)
    move(api, plant.id, 70, 80)
    move_event = newest_event(store, plant.room_id)
    api.post(f"/api/room-plants/{plant.id}/care", json={"care": "water"}, headers=HEADERS)
    water_event = newest_event(store, plant.room_id)
    before = snapshot(store, plant.room_id)
    notify.reset_mock()

    refused = undo(api, move_event.id)
    unchanged = snapshot(store, plant.room_id)
    water_undone = undo(api, water_event.id)
    move_undone = undo(api, move_event.id)

    assert refused.status_code == 409
    assert refused.json() == {"message": "Undo the later changes to this plant first"}
    assert unchanged == before
    assert water_undone.status_code == 204
    assert move_undone.status_code == 204
    assert store.get_room_plant(plant.id) == plant


def test_undo_of_an_area_rename_after_a_later_move_of_that_area_returns_409(api, store):
    area = store.list_areas(room_id_of(store))[0]
    api.patch(f"/api/areas/{area.id}", json={"label": "Lawn"}, headers=HEADERS)
    rename_event = newest_event(store, area.room_id)
    api.patch(f"/api/areas/{area.id}", json={"x_pct": 1}, headers=HEADERS)

    response = undo(api, rename_event.id)

    assert response.status_code == 409
    assert response.json() == {"message": "Undo the later changes to this area first"}
    assert store.get_feed_event(rename_event.id).undone_at is None


def test_later_events_of_other_plants_and_posts_do_not_block_an_undo(api, store):
    plant = tomato_in(store)
    other = next(rp for rp in store.list_room_plants(plant.room_id) if rp.id != plant.id)
    move(api, plant.id, 70, 80)
    move_event = newest_event(store, plant.room_id)
    move(api, other.id, 5, 5)
    api.post(f"/api/rooms/{plant.room_id}/posts", json={"text": "Looking good"}, headers=HEADERS)

    response = undo(api, move_event.id)

    assert response.status_code == 204
    assert store.get_room_plant(plant.id) == plant


# --- Limits ------------------------------------------------------------------


def test_undo_of_a_removal_into_a_room_with_50_live_plants_returns_409_garden_full(api, store, notify):
    before_plant, event = remove_plant(api, store)
    room_id = before_plant.room_id
    fill_plants(store, room_id, 50)
    before = snapshot(store, room_id)
    notify.reset_mock()

    response = undo(api, event.id)

    assert response.status_code == 409
    assert response.json() == {"message": "This garden is full (50 plants max)"}
    assert snapshot(store, room_id) == before
    assert store.get_feed_event(event.id).undone_at is None
    notify.assert_not_called()


# --- Not found ---------------------------------------------------------------


# --- Actor headers -----------------------------------------------------------


