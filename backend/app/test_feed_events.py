import uuid
from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app import live, timestamps
from app.main import app
from app.models import RoomArea
from app.store import Store, get_store

HEADERS = {"X-Device-Id": "device-1", "X-Actor-Name": "Tess"}
UNDO_HEADERS = {"X-Device-Id": "device-2", "X-Actor-Name": "Uma"}
MISSING_ID = "00000000-0000-4000-8000-000000000000"


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


def room_id_of(store, name="Elm Street Allotment"):
    return next(room.id for room in store.list_rooms() if room.name == name)


def plant_id_of(store, common_name):
    return next(plant.id for plant in store.list_plants() if plant.common_name == common_name)


def tomato_in(store):
    """A live Tomato room plant (all four intervals set) in the Elm Street room."""
    tomato_id = plant_id_of(store, "Tomato")
    return next(rp for rp in store.list_room_plants(room_id_of(store)) if rp.plant_id == tomato_id)


def area_payload(**overrides):
    return {
        "label": "Veg bed",
        "shape": "rect",
        "x_pct": 10,
        "y_pct": 20,
        "w_pct": 30,
        "h_pct": 40,
        "colour": "soil",
        **overrides,
    }


def make_area(store, room_id, **overrides):
    fields = {"id": str(uuid.uuid4()), "room_id": room_id, "deleted_at": None, **area_payload(label="Herbs")}
    area = RoomArea(**{**fields, **overrides})
    store.save_area(area)
    return area


def fill_plants(store, room_id, live_count):
    """Make the room hold exactly ``live_count`` live plants; the earlier ones become soft-deleted."""
    template = store.list_room_plants(room_id, include_deleted=True)[0].model_copy(update={"deleted_at": None})
    for room_plant in store.list_room_plants(room_id):
        store.save_room_plant(room_plant.model_copy(update={"deleted_at": timestamps.now()}))
    for _ in range(live_count):
        store.save_room_plant(template.model_copy(update={"id": str(uuid.uuid4()), "deleted_at": None}))


def fill_areas(store, room_id, live_count):
    for area in store.list_areas(room_id):
        store.save_area(area.model_copy(update={"deleted_at": timestamps.now()}))
    for index in range(live_count):
        make_area(store, room_id, label=f"Area {index}")


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


def add_area(api, room_id, **overrides):
    return api.post(f"/api/rooms/{room_id}/areas", json=area_payload(**overrides), headers=HEADERS).json()


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


def test_undo_keeps_the_payload_and_writes_no_new_feed_event(api, store):
    plant = tomato_in(store)
    move(api, plant.id, 70, 80)
    event = newest_event(store, plant.room_id)
    events_before = store.list_feed_events(plant.room_id)

    undo(api, event.id)

    events_after = store.list_feed_events(plant.room_id)
    assert [e.id for e in events_after] == [e.id for e in events_before]
    assert store.get_feed_event(event.id).undo_payload == event.undo_payload


def test_undone_event_stays_in_the_room_feed_with_undone_at_set(api, store):
    plant = tomato_in(store)
    move(api, plant.id, 70, 80)
    event = newest_event(store, plant.room_id)

    undo(api, event.id)

    feed = api.get(f"/api/rooms/{plant.room_id}").json()["feed"]
    entry = next(e for e in feed if e["id"] == event.id)
    assert entry["undone_at"] is not None
    assert entry["undo_payload"] is not None


def test_undo_sets_the_rooms_last_activity_to_undone_at(api, store):
    plant = tomato_in(store)
    move(api, plant.id, 70, 80)
    event = newest_event(store, plant.room_id)

    undo(api, event.id)

    assert store.get_room(plant.room_id).last_activity_at == store.get_feed_event(event.id).undone_at


def test_undo_calls_notify_once_for_the_room_after_the_transaction_ended(api, store, notify):
    plant = tomato_in(store)
    move(api, plant.id, 70, 80)
    event = newest_event(store, plant.room_id)
    notify.reset_mock()
    notify.open_during_call.clear()

    undo(api, event.id)

    assert [call.args for call in notify.call_args_list] == [(plant.room_id,)]
    assert notify.open_during_call == [0]


# --- restore_plant -----------------------------------------------------------


def test_undo_of_a_removed_plant_brings_it_back_into_the_room_state(api, store):
    before, event = remove_plant(api, store)

    response = undo(api, event.id)

    plants = api.get(f"/api/rooms/{before.room_id}").json()["plants"]
    restored = next(p for p in plants if p["id"] == before.id)
    assert response.status_code == 204
    assert restored["deleted_at"] is None
    assert store.get_room_plant(before.id) == before


def test_undo_of_a_move_puts_the_plant_back_where_it_was(api, store):
    plant = tomato_in(store)
    move(api, plant.id, 70, 80)

    undo(api, newest_event(store, plant.room_id).id)

    restored = store.get_room_plant(plant.id)
    assert (restored.x_pct, restored.y_pct) == (plant.x_pct, plant.y_pct)


def test_undo_of_care_restores_the_old_care_timestamps(api, store):
    plant = tomato_in(store)
    api.post(f"/api/room-plants/{plant.id}/care", json={"care": "water"}, headers=HEADERS)
    event = newest_event(store, plant.room_id)
    assert store.get_room_plant(plant.id).last_watered_at != plant.last_watered_at

    undo(api, event.id)

    assert store.get_room_plant(plant.id) == plant


def test_undo_of_an_older_move_writes_the_old_snapshot_back_over_newer_edits(api, store):
    plant = tomato_in(store)
    move(api, plant.id, 70, 80)
    first = newest_event(store, plant.room_id)
    move(api, plant.id, 5, 6)
    api.post(f"/api/room-plants/{plant.id}/care", json={"care": "feed"}, headers=HEADERS)

    undo(api, first.id)

    assert store.get_room_plant(plant.id) == plant


def test_undo_of_a_move_on_a_since_removed_plant_brings_it_back_at_the_old_position(api, store):
    plant = tomato_in(store)
    move(api, plant.id, 70, 80)
    first = newest_event(store, plant.room_id)
    api.delete(f"/api/room-plants/{plant.id}", headers=HEADERS)

    response = undo(api, first.id)

    assert response.status_code == 204
    assert store.get_room_plant(plant.id) == plant


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


def test_undo_of_an_added_plant_that_was_already_removed_keeps_its_deleted_at_and_returns_204(api, store):
    room_id = room_id_of(store)
    added = api.post(
        f"/api/rooms/{room_id}/plants", json={"plant_id": plant_id_of(store, "Tomato")}, headers=HEADERS
    ).json()
    add_event = newest_event(store, room_id)
    api.delete(f"/api/room-plants/{added['id']}", headers=HEADERS)
    deleted_at = store.get_room_plant(added["id"]).deleted_at

    response = undo(api, add_event.id)

    assert response.status_code == 204
    assert store.get_room_plant(added["id"]).deleted_at == deleted_at
    assert store.get_feed_event(add_event.id).undone_at is not None


# --- Areas -------------------------------------------------------------------


def test_undo_of_an_added_area_soft_deletes_it(api, store):
    room_id = room_id_of(store)
    added = add_area(api, room_id)

    response = undo(api, newest_event(store, room_id).id)

    areas = api.get(f"/api/rooms/{room_id}").json()["areas"]
    assert response.status_code == 204
    assert added["id"] not in [a["id"] for a in areas]
    assert store.get_area(added["id"]).deleted_at is not None


def test_undo_of_an_added_area_that_was_already_deleted_keeps_its_deleted_at_and_returns_204(api, store):
    room_id = room_id_of(store)
    added = add_area(api, room_id)
    add_event = newest_event(store, room_id)
    api.delete(f"/api/areas/{added['id']}", headers=HEADERS)
    deleted_at = store.get_area(added["id"]).deleted_at

    response = undo(api, add_event.id)

    assert response.status_code == 204
    assert store.get_area(added["id"]).deleted_at == deleted_at
    assert store.get_feed_event(add_event.id).undone_at is not None


def test_undo_of_a_deleted_area_brings_it_back_exactly(api, store):
    room_id = room_id_of(store)
    added = add_area(api, room_id)
    api.delete(f"/api/areas/{added['id']}", headers=HEADERS)

    response = undo(api, newest_event(store, room_id).id)

    areas = api.get(f"/api/rooms/{room_id}").json()["areas"]
    assert response.status_code == 204
    assert added in areas
    assert store.get_area(added["id"]).deleted_at is None


def test_undo_of_an_area_edit_writes_the_old_area_back_even_after_newer_edits(api, store):
    room_id = room_id_of(store)
    added = add_area(api, room_id)
    api.patch(f"/api/areas/{added['id']}", json={"label": "Pond", "x_pct": 55}, headers=HEADERS)
    edit = newest_event(store, room_id)
    api.patch(f"/api/areas/{added['id']}", json={"label": "Lake", "colour": "water"}, headers=HEADERS)

    undo(api, edit.id)

    assert store.get_area(added["id"]).model_dump() == {**added, "deleted_at": None}


# --- Cannot undo / already undone --------------------------------------------


def test_undo_of_a_post_returns_409_cannot_be_undone_and_changes_nothing(api, store, notify):
    room_id = room_id_of(store)
    api.post(f"/api/rooms/{room_id}/posts", json={"text": "Hello", "photo_id": None}, headers=HEADERS)
    event = newest_event(store, room_id)
    before = snapshot(store, room_id)
    notify.reset_mock()

    response = undo(api, event.id)

    assert response.status_code == 409
    assert response.json() == {"message": "This can't be undone"}
    assert snapshot(store, room_id) == before
    assert store.get_feed_event(event.id).undone_at is None
    notify.assert_not_called()


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


def test_undo_of_a_removal_into_a_room_with_49_live_plants_succeeds(api, store):
    before_plant, event = remove_plant(api, store)
    fill_plants(store, before_plant.room_id, 49)

    response = undo(api, event.id)

    assert response.status_code == 204
    assert len(store.list_room_plants(before_plant.room_id)) == 50


def test_undo_of_a_move_on_a_live_plant_is_not_blocked_in_a_room_with_50_live_plants(api, store):
    plant = tomato_in(store)
    move(api, plant.id, 70, 80)
    event = newest_event(store, plant.room_id)
    fill_plants(store, plant.room_id, 49)
    store.save_room_plant(plant.model_copy(update={"x_pct": 70, "y_pct": 80}))
    assert len(store.list_room_plants(plant.room_id)) == 50

    response = undo(api, event.id)

    assert response.status_code == 204
    assert store.get_room_plant(plant.id) == plant


def test_undo_of_an_area_delete_into_a_room_with_10_live_areas_returns_409_max_areas(api, store, notify):
    room_id = room_id_of(store)
    added = add_area(api, room_id)
    api.delete(f"/api/areas/{added['id']}", headers=HEADERS)
    event = newest_event(store, room_id)
    fill_areas(store, room_id, 10)
    before = snapshot(store, room_id)
    notify.reset_mock()

    response = undo(api, event.id)

    assert response.status_code == 409
    assert response.json() == {"message": "This garden has the maximum 10 areas"}
    assert snapshot(store, room_id) == before
    assert store.get_feed_event(event.id).undone_at is None
    notify.assert_not_called()


def test_undo_of_an_area_edit_on_a_live_area_is_not_blocked_in_a_room_with_10_live_areas(api, store):
    room_id = room_id_of(store)
    fill_areas(store, room_id, 9)
    added = add_area(api, room_id)
    api.patch(f"/api/areas/{added['id']}", json={"label": "Pond"}, headers=HEADERS)
    event = newest_event(store, room_id)
    assert len(store.list_areas(room_id)) == 10

    response = undo(api, event.id)

    assert response.status_code == 204
    assert store.get_area(added["id"]).label == "Veg bed"


def test_undo_of_an_added_plant_in_a_full_room_is_not_blocked(api, store):
    room_id = room_id_of(store)
    api.post(f"/api/rooms/{room_id}/plants", json={"plant_id": plant_id_of(store, "Tomato")}, headers=HEADERS)
    event = newest_event(store, room_id)
    fill_plants(store, room_id, 49)
    added = store.get_room_plant(event.undo_payload.room_plant_id)
    store.save_room_plant(added.model_copy(update={"deleted_at": None}))

    response = undo(api, event.id)

    assert response.status_code == 204


# --- Not found ---------------------------------------------------------------


@pytest.mark.parametrize("event_id", [MISSING_ID, "not-a-uuid", "123"])
def test_undo_of_an_unknown_or_non_uuid_event_returns_404_event_not_found(api, store, notify, event_id):
    room_id = room_id_of(store)
    before = snapshot(store, room_id)

    response = undo(api, event_id)

    assert response.status_code == 404
    assert response.json() == {"message": "Event not found"}
    assert snapshot(store, room_id) == before
    notify.assert_not_called()


# --- Actor headers -----------------------------------------------------------


@pytest.mark.parametrize(
    "headers",
    [
        pytest.param({}, id="no headers"),
        pytest.param({"X-Actor-Name": "Tess"}, id="no device id"),
        pytest.param({"X-Device-Id": "device-1"}, id="no actor name"),
        pytest.param({"X-Device-Id": "device-1", "X-Actor-Name": "  "}, id="blank actor name"),
        pytest.param({"X-Device-Id": "device-1", "X-Actor-Name": "%FF"}, id="malformed actor name"),
    ],
)
def test_undo_without_valid_actor_headers_returns_400_and_changes_nothing(api, store, notify, headers):
    plant = tomato_in(store)
    move(api, plant.id, 70, 80)
    event = newest_event(store, plant.room_id)
    before = snapshot(store, plant.room_id)
    notify.reset_mock()

    responses = [undo(api, event.id, headers=headers), undo(api, MISSING_ID, headers=headers)]

    assert [r.status_code for r in responses] == [400, 400]
    assert all(r.json()["message"] for r in responses)
    assert snapshot(store, plant.room_id) == before
    assert store.get_feed_event(event.id).undone_at is None
    notify.assert_not_called()
