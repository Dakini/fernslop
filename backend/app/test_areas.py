import uuid
from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app import live, timestamps
from app.main import app
from app.models import RoomArea
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


def _invalid_area_payloads():
    missing_label = area_payload()
    del missing_label["label"]
    return [
        pytest.param(missing_label, id="missing label"),
        pytest.param(area_payload(label="   "), id="blank label"),
        pytest.param(area_payload(w_pct=101), id="percent out of range"),
    ]


@pytest.mark.parametrize("payload", _invalid_area_payloads())
def test_add_area_with_an_invalid_body_returns_400_and_writes_nothing(api, store, notify, payload):
    room_id = room_id_of(store)
    before = snapshot(store, room_id)

    response = api.post(f"/api/rooms/{room_id}/areas", json=payload, headers=HEADERS)

    assert response.status_code == 400
    assert response.json()["message"]
    assert snapshot(store, room_id) == before
    notify.assert_not_called()


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


# --- Update ------------------------------------------------------------------


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


# --- Delete ------------------------------------------------------------------


def test_delete_area_returns_204_with_an_empty_body_and_hides_it_from_the_room(api, store):
    room_id = room_id_of(store)
    area = make_area(store, room_id)

    response = api.delete(f"/api/areas/{area.id}", headers=HEADERS)

    assert response.status_code == 204
    assert response.content == b""
    assert area.id not in [a["id"] for a in api.get(f"/api/rooms/{room_id}").json()["areas"]]
    assert store.get_area(area.id).deleted_at is not None


# --- Actor headers -------------------------------------------------------------


# --- Live notification ---------------------------------------------------------


