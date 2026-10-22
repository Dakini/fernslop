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


def clear_areas(store, room_id):
    for area in store.list_areas(room_id):
        store.save_area(area.model_copy(update={"deleted_at": timestamps.now()}))


def make_area(store, room_id, **overrides):
    """Save a live area directly in the store and return it."""
    fields = {"id": str(uuid.uuid4()), "room_id": room_id, "deleted_at": None, **area_payload(label="Herbs")}
    area = RoomArea(**{**fields, **overrides})
    store.save_area(area)
    return area


def fill_areas(store, room_id, live_count, *, deleted=0):
    clear_areas(store, room_id)
    for index in range(live_count + deleted):
        make_area(store, room_id, label=f"Area {index}", deleted_at=timestamps.now() if index >= live_count else None)


def snapshot(store, room_id):
    return (
        store.list_areas(room_id, include_deleted=True),
        store.list_feed_events(room_id),
        store.get_room(room_id).last_activity_at,
    )


def newest_event(store, room_id):
    return store.list_feed_events(room_id)[0]


# --- Add ---------------------------------------------------------------------


def test_add_area_returns_201_with_a_new_room_area(api, store):
    room_id = room_id_of(store)

    response = api.post(f"/api/rooms/{room_id}/areas", json=area_payload(label="  Veg bed  "), headers=HEADERS)

    body = response.json()
    assert response.status_code == 201
    assert str(uuid.UUID(body["id"], version=4)) == body["id"]
    assert body["room_id"] == room_id
    assert body["deleted_at"] is None
    assert body["label"] == "Veg bed"
    assert (body["shape"], body["colour"]) == ("rect", "soil")
    assert (body["x_pct"], body["y_pct"], body["w_pct"], body["h_pct"]) == (10, 20, 30, 40)


def test_add_area_shows_in_the_room_state(api, store):
    room_id = room_id_of(store)

    added = api.post(f"/api/rooms/{room_id}/areas", json=area_payload(), headers=HEADERS).json()

    assert added in api.get(f"/api/rooms/{room_id}").json()["areas"]


def test_add_area_writes_one_feed_event_with_a_restore_area_undo_payload(api, store):
    room_id = room_id_of(store)
    events_before = len(store.list_feed_events(room_id))

    added = api.post(f"/api/rooms/{room_id}/areas", json=area_payload(), headers=HEADERS).json()

    events = store.list_feed_events(room_id)
    event = events[0]
    assert len(events) == events_before + 1
    assert event.type == "area_changed"
    assert event.text == 'added the area "Veg bed"'
    assert (event.actor_name, event.device_id) == ("Tess", "device-1")
    assert event.room_plant_id is None
    assert event.undo_payload.model_dump() == {"kind": "restore_area", "area": None, "area_id": added["id"]}


def test_add_area_sets_the_rooms_last_activity_to_the_events_created_at(api, store):
    room_id = room_id_of(store)

    api.post(f"/api/rooms/{room_id}/areas", json=area_payload(), headers=HEADERS)

    assert store.get_room(room_id).last_activity_at == newest_event(store, room_id).created_at


def test_add_area_accepts_the_boundary_values(api, store):
    room_id = room_id_of(store)
    payload = area_payload(label="x" * 40, x_pct=0, y_pct=100, w_pct=100, h_pct=0.01, shape="ellipse", colour="water")

    response = api.post(f"/api/rooms/{room_id}/areas", json=payload, headers=HEADERS)

    assert response.status_code == 201
    assert response.json()["label"] == "x" * 40


def test_add_area_to_unknown_room_returns_404_room_not_found(api, store):
    response = api.post(f"/api/rooms/{MISSING_ID}/areas", json=area_payload(), headers=HEADERS)

    assert response.status_code == 404
    assert response.json() == {"message": "Room not found"}


def test_add_area_to_a_non_uuid_room_returns_404_room_not_found(api, store):
    response = api.post("/api/rooms/not-a-uuid/areas", json=area_payload(), headers=HEADERS)

    assert response.status_code == 404
    assert response.json() == {"message": "Room not found"}


def _invalid_area_payloads():
    cases = {f"missing {field}": field for field in ("label", "shape", "x_pct", "y_pct", "w_pct", "h_pct", "colour")}
    payloads = []
    for name, field in cases.items():
        payload = area_payload()
        del payload[field]
        payloads.append(pytest.param(payload, id=name))
    payloads += [
        pytest.param(area_payload(label=""), id="empty label"),
        pytest.param(area_payload(label="   "), id="whitespace label"),
        pytest.param(area_payload(label="x" * 41), id="label over 40"),
        pytest.param(area_payload(label=" " + "x" * 41 + " "), id="trimmed label over 40"),
        pytest.param(area_payload(label=None), id="null label"),
        pytest.param(area_payload(label=7), id="numeric label"),
        pytest.param(area_payload(shape="triangle"), id="unknown shape"),
        pytest.param(area_payload(colour="purple"), id="unknown colour"),
        pytest.param(area_payload(shape=None), id="null shape"),
        pytest.param(area_payload(x_pct=-1), id="x below 0"),
        pytest.param(area_payload(y_pct=100.5), id="y above 100"),
        pytest.param(area_payload(w_pct=101), id="w above 100"),
        pytest.param(area_payload(h_pct=-0.1), id="h below 0"),
        pytest.param(area_payload(w_pct=0), id="w zero"),
        pytest.param(area_payload(h_pct=0), id="h zero"),
        pytest.param(area_payload(x_pct="10"), id="string percent"),
        pytest.param(area_payload(x_pct=True), id="boolean percent"),
        pytest.param(area_payload(x_pct=None), id="null percent"),
        pytest.param({}, id="empty body"),
    ]
    return payloads


@pytest.mark.parametrize("payload", _invalid_area_payloads())
def test_add_area_with_an_invalid_body_returns_400_and_writes_nothing(api, store, notify, payload):
    room_id = room_id_of(store)
    before = snapshot(store, room_id)

    response = api.post(f"/api/rooms/{room_id}/areas", json=payload, headers=HEADERS)

    assert response.status_code == 400
    assert response.json()["message"]
    assert snapshot(store, room_id) == before
    notify.assert_not_called()


def test_add_area_with_a_blank_label_says_an_area_needs_a_label(api, store):
    response = api.post(f"/api/rooms/{room_id_of(store)}/areas", json=area_payload(label="  "), headers=HEADERS)

    assert response.json() == {"message": "An area needs a label"}


def test_add_area_out_of_range_percent_is_rejected_not_clamped(api, store):
    room_id = room_id_of(store)

    api.post(f"/api/rooms/{room_id}/areas", json=area_payload(x_pct=150), headers=HEADERS)

    assert all(area.x_pct != 100 for area in store.list_areas(room_id))


@pytest.mark.parametrize("raw", ["not json", "[1]", "null", ""])
def test_add_area_with_a_body_that_is_not_a_json_object_returns_400(api, store, raw):
    response = api.post(
        f"/api/rooms/{room_id_of(store)}/areas",
        content=raw,
        headers={**HEADERS, "Content-Type": "application/json"},
    )

    assert response.status_code == 400
    assert "message" in response.json()


# --- Area limit --------------------------------------------------------------


def test_add_area_to_a_room_with_10_live_areas_returns_409_and_writes_nothing(api, store, notify):
    room_id = room_id_of(store)
    fill_areas(store, room_id, 10)
    before = snapshot(store, room_id)

    response = api.post(f"/api/rooms/{room_id}/areas", json=area_payload(), headers=HEADERS)

    assert response.status_code == 409
    assert response.json() == {"message": "This garden has the maximum 10 areas"}
    assert snapshot(store, room_id) == before
    notify.assert_not_called()


def test_add_area_to_a_room_with_10_areas_one_deleted_succeeds(api, store):
    room_id = room_id_of(store)
    fill_areas(store, room_id, 9, deleted=1)

    response = api.post(f"/api/rooms/{room_id}/areas", json=area_payload(), headers=HEADERS)

    assert response.status_code == 201
    assert len(store.list_areas(room_id)) == 10


def test_add_area_counts_only_the_rooms_own_areas(api, store):
    room_id = room_id_of(store)
    other_id = next(room.id for room in store.list_rooms() if room.id != room_id)
    fill_areas(store, other_id, 10)
    clear_areas(store, room_id)

    response = api.post(f"/api/rooms/{room_id}/areas", json=area_payload(), headers=HEADERS)

    assert response.status_code == 201


# --- Update ------------------------------------------------------------------


def test_update_area_changes_only_the_fields_sent_and_returns_the_full_area(api, store):
    area = make_area(store, room_id_of(store))

    response = api.patch(f"/api/areas/{area.id}", json={"colour": "water", "x_pct": 55}, headers=HEADERS)

    expected = {**area.model_dump(mode="json"), "colour": "water", "x_pct": 55}
    assert response.status_code == 200
    assert response.json() == expected
    assert store.get_area(area.id).model_dump(mode="json") == expected


def test_update_area_trims_the_label(api, store):
    area = make_area(store, room_id_of(store))

    response = api.patch(f"/api/areas/{area.id}", json={"label": "  Pond "}, headers=HEADERS)

    assert response.json()["label"] == "Pond"


def test_update_area_writes_one_event_whose_undo_payload_holds_the_area_before(api, store):
    room_id = room_id_of(store)
    area = make_area(store, room_id)
    events_before = len(store.list_feed_events(room_id))

    api.patch(f"/api/areas/{area.id}", json={"label": "Lawn", "w_pct": 5}, headers=HEADERS)

    events = store.list_feed_events(room_id)
    event = events[0]
    assert len(events) == events_before + 1
    assert event.type == "area_changed"
    assert (event.actor_name, event.device_id) == ("Tess", "device-1")
    assert event.undo_payload.model_dump(mode="json") == {
        "kind": "restore_area",
        "area": area.model_dump(mode="json"),
        "area_id": area.id,
    }
    assert store.get_room(room_id).last_activity_at == event.created_at


@pytest.mark.parametrize(
    ("patch", "text"),
    [
        ({"label": "Herbs 2"}, 'renamed "Herbs" to "Herbs 2"'),
        ({"label": "Herbs 2", "w_pct": 5, "x_pct": 1, "shape": "ellipse"}, 'renamed "Herbs" to "Herbs 2"'),
        ({"w_pct": 5}, 'resized the area "Herbs"'),
        ({"h_pct": 5, "x_pct": 1, "colour": "clay"}, 'resized the area "Herbs"'),
        ({"x_pct": 1}, 'moved the area "Herbs"'),
        ({"y_pct": 1, "shape": "ellipse"}, 'moved the area "Herbs"'),
        ({"shape": "ellipse"}, 'changed the area "Herbs"'),
        ({"colour": "clay"}, 'changed the area "Herbs"'),
        ({"colour": "clay", "shape": "ellipse"}, 'changed the area "Herbs"'),
    ],
)
def test_update_area_event_text_follows_the_first_matching_rule(api, store, patch, text):
    room_id = room_id_of(store)
    area = make_area(store, room_id)

    api.patch(f"/api/areas/{area.id}", json=patch, headers=HEADERS)

    assert newest_event(store, room_id).text == text


def test_update_area_sent_fields_equal_to_current_do_not_count_as_changes(api, store):
    room_id = room_id_of(store)
    area = make_area(store, room_id, x_pct=10)

    api.patch(f"/api/areas/{area.id}", json={"label": "Herbs", "x_pct": 10, "colour": "water"}, headers=HEADERS)

    assert newest_event(store, room_id).text == 'changed the area "Herbs"'


def test_update_area_with_identical_values_returns_200_and_writes_nothing(api, store, notify):
    room_id = room_id_of(store)
    area = make_area(store, room_id)
    before = snapshot(store, room_id)

    response = api.patch(f"/api/areas/{area.id}", json={"label": " Herbs ", "x_pct": 10, "shape": "rect"}, headers=HEADERS)

    assert response.status_code == 200
    assert response.json() == area.model_dump(mode="json")
    assert snapshot(store, room_id) == before
    notify.assert_not_called()


@pytest.mark.parametrize(
    "patch",
    [
        pytest.param({}, id="empty body"),
        pytest.param({"colour_name": "soil", "id": "x"}, id="no known fields"),
        pytest.param({"label": None}, id="null label"),
        pytest.param({"x_pct": None}, id="null percent"),
        pytest.param({"label": "Pond", "shape": None}, id="null among valid"),
        pytest.param({"label": ""}, id="empty label"),
        pytest.param({"label": "   "}, id="whitespace label"),
        pytest.param({"label": "x" * 41}, id="label over 40"),
        pytest.param({"shape": "triangle"}, id="unknown shape"),
        pytest.param({"colour": "purple"}, id="unknown colour"),
        pytest.param({"x_pct": -1}, id="x below 0"),
        pytest.param({"y_pct": 101}, id="y above 100"),
        pytest.param({"w_pct": 0}, id="w zero"),
        pytest.param({"h_pct": 0}, id="h zero"),
        pytest.param({"w_pct": 120, "label": "Pond"}, id="invalid among valid"),
        pytest.param({"x_pct": "10"}, id="string percent"),
        pytest.param({"x_pct": False}, id="boolean percent"),
    ],
)
def test_update_area_with_an_invalid_body_returns_400_and_changes_nothing(api, store, notify, patch):
    room_id = room_id_of(store)
    area = make_area(store, room_id)
    before = snapshot(store, room_id)

    response = api.patch(f"/api/areas/{area.id}", json=patch, headers=HEADERS)

    assert response.status_code == 400
    assert response.json()["message"]
    assert snapshot(store, room_id) == before
    assert store.get_area(area.id) == area
    notify.assert_not_called()


@pytest.mark.parametrize("raw", ["not json", "[1]", "null", ""])
def test_update_area_with_a_body_that_is_not_a_json_object_returns_400(api, store, raw):
    area = make_area(store, room_id_of(store))

    response = api.patch(f"/api/areas/{area.id}", content=raw, headers={**HEADERS, "Content-Type": "application/json"})

    assert response.status_code == 400


def test_update_area_ignores_unknown_fields_alongside_known_ones(api, store):
    area = make_area(store, room_id_of(store))

    response = api.patch(f"/api/areas/{area.id}", json={"label": "Pond", "id": "hacked", "room_id": "x"}, headers=HEADERS)

    assert response.status_code == 200
    assert (response.json()["id"], response.json()["room_id"]) == (area.id, area.room_id)


@pytest.mark.parametrize("area_id", [MISSING_ID, "not-a-uuid"])
def test_update_area_unknown_or_non_uuid_id_returns_404_area_not_found(api, store, notify, area_id):
    response = api.patch(f"/api/areas/{area_id}", json={"label": "Pond"}, headers=HEADERS)

    assert response.status_code == 404
    assert response.json() == {"message": "Area not found"}
    notify.assert_not_called()


def test_update_area_on_a_soft_deleted_area_returns_404_and_writes_nothing(api, store, notify):
    room_id = room_id_of(store)
    area = make_area(store, room_id, deleted_at=timestamps.now())
    before = snapshot(store, room_id)

    response = api.patch(f"/api/areas/{area.id}", json={"label": "Pond"}, headers=HEADERS)

    assert response.status_code == 404
    assert response.json() == {"message": "Area not found"}
    assert snapshot(store, room_id) == before
    notify.assert_not_called()


# --- Delete ------------------------------------------------------------------


def test_delete_area_returns_204_with_an_empty_body_and_hides_it_from_the_room(api, store):
    room_id = room_id_of(store)
    area = make_area(store, room_id)

    response = api.delete(f"/api/areas/{area.id}", headers=HEADERS)

    assert response.status_code == 204
    assert response.content == b""
    assert area.id not in [a["id"] for a in api.get(f"/api/rooms/{room_id}").json()["areas"]]
    assert store.get_area(area.id).deleted_at is not None


def test_delete_area_writes_one_event_with_the_area_as_it_was_before(api, store):
    room_id = room_id_of(store)
    area = make_area(store, room_id)
    events_before = len(store.list_feed_events(room_id))

    api.delete(f"/api/areas/{area.id}", headers=HEADERS)

    events = store.list_feed_events(room_id)
    event = events[0]
    assert len(events) == events_before + 1
    assert event.type == "area_changed"
    assert event.text == 'removed the area "Herbs"'
    assert (event.actor_name, event.device_id) == ("Tess", "device-1")
    assert event.undo_payload.model_dump(mode="json") == {
        "kind": "restore_area",
        "area": area.model_dump(mode="json"),
        "area_id": area.id,
    }
    assert store.get_room(room_id).last_activity_at == event.created_at


def test_delete_area_twice_returns_404_area_not_found_and_writes_nothing(api, store, notify):
    room_id = room_id_of(store)
    area = make_area(store, room_id)
    api.delete(f"/api/areas/{area.id}", headers=HEADERS)
    before = snapshot(store, room_id)
    notify.reset_mock()

    response = api.delete(f"/api/areas/{area.id}", headers=HEADERS)

    assert response.status_code == 404
    assert response.json() == {"message": "Area not found"}
    assert snapshot(store, room_id) == before
    notify.assert_not_called()


@pytest.mark.parametrize("area_id", [MISSING_ID, "not-a-uuid"])
def test_delete_area_unknown_or_non_uuid_id_returns_404_area_not_found(api, store, notify, area_id):
    response = api.delete(f"/api/areas/{area_id}", headers=HEADERS)

    assert response.status_code == 404
    assert response.json() == {"message": "Area not found"}
    notify.assert_not_called()


# --- Actor headers -------------------------------------------------------------


@pytest.mark.parametrize(
    "headers",
    [
        pytest.param({}, id="no headers"),
        pytest.param({"X-Actor-Name": "Tess"}, id="no device id"),
        pytest.param({"X-Device-Id": "device-1"}, id="no actor name"),
        pytest.param({"X-Device-Id": "device-1", "X-Actor-Name": "  "}, id="blank actor name"),
    ],
)
def test_area_endpoints_without_actor_headers_return_400_and_write_nothing(api, store, notify, headers):
    room_id = room_id_of(store)
    area = make_area(store, room_id)
    before = snapshot(store, room_id)

    responses = [
        api.post(f"/api/rooms/{room_id}/areas", json=area_payload(), headers=headers),
        api.patch(f"/api/areas/{area.id}", json={"label": "Pond"}, headers=headers),
        api.delete(f"/api/areas/{area.id}", headers=headers),
    ]

    assert [r.status_code for r in responses] == [400, 400, 400]
    assert all(r.json()["message"] for r in responses)
    assert snapshot(store, room_id) == before
    notify.assert_not_called()


# --- Live notification ---------------------------------------------------------


def test_each_successful_area_change_calls_notify_once_after_the_transaction_ended(api, store, notify):
    room_id = room_id_of(store)

    added = api.post(f"/api/rooms/{room_id}/areas", json=area_payload(), headers=HEADERS).json()
    api.patch(f"/api/areas/{added['id']}", json={"label": "Pond"}, headers=HEADERS)
    api.delete(f"/api/areas/{added['id']}", headers=HEADERS)

    assert [call.args for call in notify.call_args_list] == [(room_id,)] * 3
    assert notify.open_during_call == [0, 0, 0]
