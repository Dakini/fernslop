import uuid
from contextlib import contextmanager
from datetime import timedelta
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app import live, timestamps
from app.main import app
from app.store import Store, get_store

HEADERS = {"X-Device-Id": "device-1", "X-Actor-Name": "Tess"}
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


def snapshot(store, room_id):
    return (
        store.list_room_plants(room_id, include_deleted=True),
        store.list_feed_events(room_id),
        store.get_room(room_id).last_activity_at,
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


def test_add_plant_shows_in_the_room_state(api, store):
    room_id = room_id_of(store)

    added = api.post(f"/api/rooms/{room_id}/plants", json=add_payload(store), headers=HEADERS).json()

    plants = api.get(f"/api/rooms/{room_id}").json()["plants"]
    assert added in plants


def test_add_plant_to_unknown_room_returns_404_room_not_found(api, store):
    response = api.post(f"/api/rooms/{MISSING_ID}/plants", json=add_payload(store), headers=HEADERS)

    assert response.status_code == 404
    assert response.json() == {"message": "Room not found"}


def test_add_plant_with_unknown_plant_id_returns_404_plant_not_found(api, store):
    response = api.post(f"/api/rooms/{room_id_of(store)}/plants", json={"plant_id": "nope"}, headers=HEADERS)

    assert response.status_code == 404
    assert response.json() == {"message": "Plant not found"}


@pytest.mark.parametrize("body", [{}, {"plant_id": None}, {"plant_id": 7}, {"plant_id": ["a"]}, {"plant_id": True}])
def test_add_plant_with_missing_or_non_string_plant_id_returns_400(api, store, body):
    response = api.post(f"/api/rooms/{room_id_of(store)}/plants", json=body, headers=HEADERS)

    assert response.status_code == 400
    assert response.json()["message"]


@pytest.mark.parametrize("raw", ["not json", "[1]", "null", ""])
def test_add_plant_with_a_body_that_is_not_a_json_object_returns_400(api, store, raw):
    response = api.post(
        f"/api/rooms/{room_id_of(store)}/plants",
        content=raw,
        headers={**HEADERS, "Content-Type": "application/json"},
    )

    assert response.status_code == 400


# --- Garden limit ------------------------------------------------------------


def test_add_plant_to_a_room_with_50_live_plants_returns_409_garden_full(api, store):
    room_id = room_id_of(store)
    fill_room(store, room_id, 50)

    response = api.post(f"/api/rooms/{room_id}/plants", json=add_payload(store), headers=HEADERS)

    assert response.status_code == 409
    assert response.json() == {"message": "This garden is full (50 plants max)"}


def test_add_plant_to_a_room_with_49_live_and_many_deleted_plants_succeeds(api, store):
    room_id = room_id_of(store)
    fill_room(store, room_id, 49, deleted=10)

    response = api.post(f"/api/rooms/{room_id}/plants", json=add_payload(store), headers=HEADERS)

    assert response.status_code == 201
    assert len(store.list_room_plants(room_id)) == 50


def test_add_plant_to_a_full_room_changes_nothing_and_does_not_notify(api, store, notify):
    room_id = room_id_of(store)
    fill_room(store, room_id, 50)
    before = snapshot(store, room_id)

    api.post(f"/api/rooms/{room_id}/plants", json=add_payload(store), headers=HEADERS)

    assert snapshot(store, room_id) == before
    notify.assert_not_called()


# --- Move ------------------------------------------------------------------


def test_move_plant_returns_200_with_the_updated_room_plant(api, store):
    original = live_room_plant(store)

    response = api.patch(f"/api/room-plants/{original.id}", json={"x_pct": 12, "y_pct": 34}, headers=HEADERS)

    body = response.json()
    assert response.status_code == 200
    assert (body["x_pct"], body["y_pct"]) == (12, 34)
    assert body["id"] == original.id
    assert store.get_room_plant(original.id).x_pct == 12


def test_move_plant_clamps_coordinates_to_0_and_100(api, store):
    original = live_room_plant(store)

    body = api.patch(f"/api/room-plants/{original.id}", json={"x_pct": -5, "y_pct": 250}, headers=HEADERS).json()

    assert (body["x_pct"], body["y_pct"]) == (0, 100)


def test_move_plant_keeps_float_coordinates(api, store):
    original = live_room_plant(store)

    body = api.patch(f"/api/room-plants/{original.id}", json={"x_pct": 12.345, "y_pct": 99.5}, headers=HEADERS).json()

    assert (body["x_pct"], body["y_pct"]) == (12.345, 99.5)


@pytest.mark.parametrize(
    "body",
    [
        {"y_pct": 5},
        {"x_pct": 5},
        {"x_pct": "5", "y_pct": 5},
        {"x_pct": 5, "y_pct": None},
        {"x_pct": True, "y_pct": 5},
        {"x_pct": 5, "y_pct": False},
        {"x_pct": [1], "y_pct": 5},
    ],
)
def test_move_plant_with_a_missing_non_number_boolean_or_null_coordinate_returns_400(api, store, body):
    original = live_room_plant(store)
    before = snapshot(store, original.room_id)

    response = api.patch(f"/api/room-plants/{original.id}", json=body, headers=HEADERS)

    assert response.status_code == 400
    assert snapshot(store, original.room_id) == before


@pytest.mark.parametrize("raw", ['{"x_pct": NaN, "y_pct": 1}', '{"x_pct": 1, "y_pct": 1e999}'])
def test_move_plant_with_a_non_finite_coordinate_returns_400(api, store, raw):
    original = live_room_plant(store)

    response = api.patch(
        f"/api/room-plants/{original.id}", content=raw, headers={**HEADERS, "Content-Type": "application/json"}
    )

    assert response.status_code == 400


def test_move_plant_clamps_integers_too_large_for_a_float(api, store):
    original = live_room_plant(store)
    raw = '{"x_pct": 1' + "0" * 400 + ', "y_pct": -1' + "0" * 400 + "}"

    response = api.patch(
        f"/api/room-plants/{original.id}", content=raw, headers={**HEADERS, "Content-Type": "application/json"}
    )

    assert response.status_code == 200
    assert (response.json()["x_pct"], response.json()["y_pct"]) == (100, 0)


# --- Remove ----------------------------------------------------------------


def test_remove_plant_returns_204_with_an_empty_body_and_sets_deleted_at(api, store):
    original = live_room_plant(store)

    response = api.delete(f"/api/room-plants/{original.id}", headers=HEADERS)

    assert response.status_code == 204
    assert response.content == b""
    assert store.get_room_plant(original.id).deleted_at is not None


def test_remove_plant_takes_it_out_of_the_room_state(api, store):
    original = live_room_plant(store)

    api.delete(f"/api/room-plants/{original.id}", headers=HEADERS)

    plants = api.get(f"/api/rooms/{original.room_id}").json()["plants"]
    assert original.id not in [plant["id"] for plant in plants]


def test_remove_plant_twice_returns_404_plant_gone(api, store):
    original = live_room_plant(store)
    api.delete(f"/api/room-plants/{original.id}", headers=HEADERS)

    response = api.delete(f"/api/room-plants/{original.id}", headers=HEADERS)

    assert response.status_code == 404
    assert response.json() == {"message": "Plant is no longer in this garden"}


def test_remove_unknown_room_plant_returns_404_plant_gone(api):
    response = api.delete(f"/api/room-plants/{MISSING_ID}", headers=HEADERS)

    assert response.status_code == 404
    assert response.json() == {"message": "Plant is no longer in this garden"}


def test_move_a_removed_plant_returns_404_plant_gone(api, store):
    original = live_room_plant(store)
    api.delete(f"/api/room-plants/{original.id}", headers=HEADERS)

    response = api.patch(f"/api/room-plants/{original.id}", json={"x_pct": 1, "y_pct": 1}, headers=HEADERS)

    assert response.status_code == 404
    assert response.json() == {"message": "Plant is no longer in this garden"}


def test_care_on_a_removed_plant_returns_404_plant_gone(api, store):
    original = live_room_plant(store)
    api.delete(f"/api/room-plants/{original.id}", headers=HEADERS)

    response = api.post(f"/api/room-plants/{original.id}/care", json={"care": "water"}, headers=HEADERS)

    assert response.status_code == 404
    assert response.json() == {"message": "Plant is no longer in this garden"}


def test_move_unknown_room_plant_returns_404_plant_gone(api):
    response = api.patch(f"/api/room-plants/{MISSING_ID}", json={"x_pct": 1, "y_pct": 1}, headers=HEADERS)

    assert response.status_code == 404
    assert response.json() == {"message": "Plant is no longer in this garden"}


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


@pytest.mark.parametrize("care", list(CARE_FIELDS))
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


def test_care_with_an_interval_of_none_returns_422_naming_the_care(api, store):
    # Lettuce has no feed interval in the seed reference table.
    lettuce = plant_id_of(store, "Lettuce")
    room_plant = tomato_in(store).model_copy(update={"id": str(uuid.uuid4()), "plant_id": lettuce})
    store.save_room_plant(room_plant)

    response = api.post(f"/api/room-plants/{room_plant.id}/care", json={"care": "feed"}, headers=HEADERS)

    assert response.status_code == 422
    assert response.json() == {"message": "No feed data for this plant"}


def test_care_with_an_interval_of_0_returns_422_naming_the_care(api, store, monkeypatch):
    tomato = tomato_in(store)
    real_get_plant = store.get_plant
    # The store has no plant writer, so serve the Tomato row with a 0 harvest interval.
    monkeypatch.setattr(
        store, "get_plant", lambda pid: real_get_plant(pid).model_copy(update={"harvest_every_days": 0})
    )

    response = api.post(f"/api/room-plants/{tomato.id}/care", json={"care": "harvest"}, headers=HEADERS)

    assert response.status_code == 422
    assert response.json() == {"message": "No harvest data for this plant"}


@pytest.mark.parametrize("body", [{}, {"care": None}, {"care": "dance"}, {"care": "WATER"}, {"care": 1}, {"care": ["water"]}])
def test_care_with_a_missing_or_unknown_care_returns_400_not_422(api, store, body):
    tomato = tomato_in(store)

    response = api.post(f"/api/room-plants/{tomato.id}/care", json=body, headers=HEADERS)

    assert response.status_code == 400
    assert response.json()["message"]


# --- Feed events -------------------------------------------------------------


def test_add_plant_writes_one_plant_added_event_first_in_the_room_state(api, store):
    room_id = room_id_of(store)
    before_count = len(store.list_feed_events(room_id))

    added = api.post(f"/api/rooms/{room_id}/plants", json=add_payload(store), headers=HEADERS).json()

    feed = api.get(f"/api/rooms/{room_id}").json()["feed"]
    assert len(feed) == before_count + 1
    assert feed[0] | {"id": feed[0]["id"]} == {
        "id": feed[0]["id"],
        "room_id": room_id,
        "type": "plant_added",
        "actor_name": "Tess",
        "device_id": "device-1",
        "room_plant_id": added["id"],
        "text": "added a Tomato",
        "photo_url": None,
        "undo_payload": {"kind": "delete_plant", "room_plant_id": added["id"]},
        "undone_at": None,
        "created_at": feed[0]["created_at"],
    }


def test_move_writes_a_plant_moved_event_with_the_plant_as_it_was_before(api, store):
    original = live_room_plant(store)
    expected_before = original.model_dump(mode="json")

    api.patch(f"/api/room-plants/{original.id}", json={"x_pct": 1, "y_pct": 2}, headers=HEADERS)

    event = api.get(f"/api/rooms/{original.room_id}").json()["feed"][0]
    assert event["type"] == "plant_moved"
    assert event["room_plant_id"] == original.id
    assert event["undo_payload"] == {"kind": "restore_plant", "room_plant": expected_before}
    assert event["undone_at"] is None


def test_move_text_uses_the_common_name_or_else_the_nickname(api, store):
    original = live_room_plant(store)
    common_name = store.get_plant(original.plant_id).common_name

    api.patch(f"/api/room-plants/{original.id}", json={"x_pct": 1, "y_pct": 2}, headers=HEADERS)
    store.save_room_plant(store.get_room_plant(original.id).model_copy(update={"nickname": "Big Red"}))
    api.patch(f"/api/room-plants/{original.id}", json={"x_pct": 3, "y_pct": 4}, headers=HEADERS)

    texts = [event.text for event in store.list_feed_events(original.room_id)[:2]]
    assert texts == ["moved the Big Red", f"moved the {common_name}"]


def test_remove_writes_a_plant_removed_event_restoring_the_live_plant(api, store):
    original = live_room_plant(store)
    expected_before = original.model_dump(mode="json")
    name = store.get_plant(original.plant_id).common_name

    api.delete(f"/api/room-plants/{original.id}", headers=HEADERS)

    event = api.get(f"/api/rooms/{original.room_id}").json()["feed"][0]
    assert event["type"] == "plant_removed"
    assert event["text"] == f"removed the {name}"
    assert event["undo_payload"] == {"kind": "restore_plant", "room_plant": expected_before}
    assert expected_before["deleted_at"] is None


@pytest.mark.parametrize("care, verb", [("water", "watered"), ("feed", "fed"), ("prune", "pruned"), ("harvest", "harvested")])
def test_care_writes_a_care_done_event_with_the_matching_text_and_prior_snapshot(api, store, care, verb):
    tomato = tomato_in(store)
    expected_before = tomato.model_dump(mode="json")

    api.post(f"/api/room-plants/{tomato.id}/care", json={"care": care}, headers=HEADERS)

    event = api.get(f"/api/rooms/{tomato.room_id}").json()["feed"][0]
    assert event["type"] == "care_done"
    assert event["text"] == f"{verb} the Tomato"
    assert event["actor_name"] == "Tess"
    assert event["device_id"] == "device-1"
    assert event["undo_payload"] == {"kind": "restore_plant", "room_plant": expected_before}


def test_each_success_writes_exactly_one_feed_event(api, store):
    original = live_room_plant(store)
    room_id = original.room_id
    count = len(store.list_feed_events(room_id))

    api.patch(f"/api/room-plants/{original.id}", json={"x_pct": 1, "y_pct": 1}, headers=HEADERS)
    api.post(f"/api/rooms/{room_id}/plants", json=add_payload(store), headers=HEADERS)
    api.delete(f"/api/room-plants/{original.id}", headers=HEADERS)

    assert len(store.list_feed_events(room_id)) == count + 3


@pytest.mark.parametrize("action", ["add", "move", "remove", "care"])
def test_last_activity_at_equals_the_new_events_created_at(api, store, action):
    tomato = tomato_in(store)
    room_id = tomato.room_id
    calls = {
        "add": lambda: api.post(f"/api/rooms/{room_id}/plants", json=add_payload(store), headers=HEADERS),
        "move": lambda: api.patch(f"/api/room-plants/{tomato.id}", json={"x_pct": 1, "y_pct": 1}, headers=HEADERS),
        "remove": lambda: api.delete(f"/api/room-plants/{tomato.id}", headers=HEADERS),
        "care": lambda: api.post(f"/api/room-plants/{tomato.id}/care", json={"care": "water"}, headers=HEADERS),
    }
    old_activity = store.get_room(room_id).last_activity_at

    calls[action]()

    newest = store.list_feed_events(room_id)[0]
    assert store.get_room(room_id).last_activity_at == newest.created_at
    assert newest.created_at > old_activity


def test_care_timestamp_and_event_share_the_requests_single_clock_reading(api, store):
    tomato = tomato_in(store)

    body = api.post(f"/api/room-plants/{tomato.id}/care", json={"care": "water"}, headers=HEADERS).json()

    assert body["last_watered_at"] == store.list_feed_events(tomato.room_id)[0].created_at.strftime(
        "%Y-%m-%dT%H:%M:%S.%f"
    )[:-3] + "Z"


# --- Actor headers -----------------------------------------------------------


def all_four_calls(api, store):
    tomato = tomato_in(store)
    room_id = tomato.room_id
    return {
        "add": lambda h: api.post(f"/api/rooms/{room_id}/plants", json=add_payload(store), headers=h),
        "move": lambda h: api.patch(f"/api/room-plants/{tomato.id}", json={"x_pct": 1, "y_pct": 1}, headers=h),
        "remove": lambda h: api.delete(f"/api/room-plants/{tomato.id}", headers=h),
        "care": lambda h: api.post(f"/api/room-plants/{tomato.id}/care", json={"care": "water"}, headers=h),
    }, room_id


BAD_HEADERS = {
    "no headers": {},
    "no device id": {"X-Actor-Name": "Tess"},
    "no actor name": {"X-Device-Id": "device-1"},
    "blank device id": {"X-Device-Id": "  ", "X-Actor-Name": "Tess"},
    "blank actor name": {"X-Device-Id": "device-1", "X-Actor-Name": " "},
    "overlong actor name": {"X-Device-Id": "device-1", "X-Actor-Name": "x" * 41},
    "bad percent encoding": {"X-Device-Id": "device-1", "X-Actor-Name": "%FF"},
}


@pytest.mark.parametrize("action", ["add", "move", "remove", "care"])
@pytest.mark.parametrize("headers", list(BAD_HEADERS.values()), ids=list(BAD_HEADERS))
def test_missing_or_malformed_actor_headers_return_400_and_change_nothing(api, store, notify, action, headers):
    calls, room_id = all_four_calls(api, store)
    before = snapshot(store, room_id)

    response = calls[action](headers)

    assert response.status_code == 400
    assert snapshot(store, room_id) == before
    notify.assert_not_called()


def test_percent_encoded_actor_name_is_decoded_in_the_event_and_plant(api, store):
    room_id = room_id_of(store)
    headers = {"X-Device-Id": "d", "X-Actor-Name": "Ren%C3%A9e"}

    added = api.post(f"/api/rooms/{room_id}/plants", json=add_payload(store), headers=headers).json()

    assert added["added_by_name"] == "Renée"
    assert store.list_feed_events(room_id)[0].actor_name == "Renée"


# --- Failures leave no trace; successes notify once ---------------------------


def failing_requests(api, store):
    tomato = tomato_in(store)
    room_id = tomato.room_id
    removed = tomato.model_copy(update={"id": str(uuid.uuid4()), "deleted_at": timestamps.now()})
    store.save_room_plant(removed)
    return room_id, {
        "add unknown room": lambda: api.post(f"/api/rooms/{MISSING_ID}/plants", json=add_payload(store), headers=HEADERS),
        "add unknown plant": lambda: api.post(f"/api/rooms/{room_id}/plants", json={"plant_id": "x"}, headers=HEADERS),
        "add bad body": lambda: api.post(f"/api/rooms/{room_id}/plants", json={}, headers=HEADERS),
        "move bad body": lambda: api.patch(f"/api/room-plants/{tomato.id}", json={"x_pct": 1}, headers=HEADERS),
        "move gone": lambda: api.patch(f"/api/room-plants/{removed.id}", json={"x_pct": 1, "y_pct": 1}, headers=HEADERS),
        "remove gone": lambda: api.delete(f"/api/room-plants/{removed.id}", headers=HEADERS),
        "care gone": lambda: api.post(f"/api/room-plants/{removed.id}/care", json={"care": "water"}, headers=HEADERS),
        "care bad": lambda: api.post(f"/api/room-plants/{tomato.id}/care", json={"care": "x"}, headers=HEADERS),
    }


@pytest.mark.parametrize(
    "name",
    ["add unknown room", "add unknown plant", "add bad body", "move bad body", "move gone", "remove gone", "care gone", "care bad"],
)
def test_every_4xx_leaves_plants_feed_and_activity_untouched_and_does_not_notify(api, store, notify, name):
    room_id, requests = failing_requests(api, store)
    before = snapshot(store, room_id)

    response = requests[name]()

    assert 400 <= response.status_code < 500
    assert snapshot(store, room_id) == before
    notify.assert_not_called()


def test_a_422_care_leaves_everything_untouched_and_does_not_notify(api, store, notify):
    lettuce = tomato_in(store).model_copy(update={"id": str(uuid.uuid4()), "plant_id": plant_id_of(store, "Lettuce")})
    store.save_room_plant(lettuce)
    before = snapshot(store, lettuce.room_id)

    response = api.post(f"/api/room-plants/{lettuce.id}/care", json={"care": "feed"}, headers=HEADERS)

    assert response.status_code == 422
    assert snapshot(store, lettuce.room_id) == before
    notify.assert_not_called()


@pytest.mark.parametrize("action", ["add", "move", "remove", "care"])
def test_every_success_notifies_once_for_the_room_after_the_transaction_ends(api, store, notify, action):
    calls, room_id = all_four_calls(api, store)

    response = calls[action](HEADERS)

    assert response.status_code < 300
    notify.assert_called_once_with(room_id)
    assert notify.open_during_call == [0]


def test_live_notify_is_a_no_op_by_default():
    assert live.notify("any-room") is None
