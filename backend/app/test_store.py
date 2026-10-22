from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import FeedEvent, Room, RoomPlant, StoredFollow, StoredPhoto
from app.sqlite_store import SqliteStore
from app.store import Store, get_store

T0 = datetime(2026, 10, 22, 9, 30, 0, tzinfo=UTC)


# --- Factories ---------------------------------------------------------------


def make_room(id="room-1", **overrides) -> Room:
    fields = dict(id=id, name="Test room", description="", region="", created_at=T0, last_activity_at=T0)
    return Room(**{**fields, **overrides})


def make_room_plant(id="rp-1", room_id="room-1", **overrides) -> RoomPlant:
    fields = dict(
        id=id,
        room_id=room_id,
        plant_id="plant-tomato",
        nickname=None,
        x_pct=10,
        y_pct=20,
        last_watered_at=None,
        last_fed_at=None,
        last_pruned_at=None,
        last_harvested_at=None,
        added_by_name="Tester",
        created_at=T0,
        deleted_at=None,
    )
    return RoomPlant(**{**fields, **overrides})


def make_event(id="ev-1", room_id="room-1", **overrides) -> FeedEvent:
    fields = dict(
        id=id,
        room_id=room_id,
        type="post",
        actor_name="Tester",
        device_id="device-1",
        room_plant_id=None,
        text="hello",
        photo_url=None,
        undo_payload=None,
        undone_at=None,
        created_at=T0,
    )
    return FeedEvent(**{**fields, **overrides})


def make_follow(id="f-1", room_id="room-1", **overrides) -> StoredFollow:
    fields = dict(id=id, room_id=room_id, email="a@example.com", created_at=T0, unsubscribe_token="tok-1")
    return StoredFollow(**{**fields, **overrides})


def make_photo(id="photo-1", **overrides) -> StoredPhoto:
    fields = dict(id=id, url=f"/api/photos/{id}", content_type="image/png", created_at=T0, data=b"abc")
    return StoredPhoto(**{**fields, **overrides})


# Every behaviour test below runs against both stores through this one fixture.
@pytest.fixture(params=["memory", "sqlite"])
def new_store(request, tmp_path):
    """A factory: ``new_store()`` is seeded, ``new_store(seed=False)`` is empty."""
    if request.param == "memory":
        return lambda seed=True: Store(seed=seed)
    return lambda seed=True: SqliteStore(tmp_path / "test.db", seed=seed)


# --- Protocol and construction -----------------------------------------------


def test_store_built_with_seed_has_the_seed(new_store):
    fresh = new_store()

    assert len(fresh.list_plants()) == 51
    assert len(fresh.list_rooms()) == 3


# --- Plants ------------------------------------------------------------------


# --- Rooms -------------------------------------------------------------------


def test_save_room_inserts_and_get_room_returns_it(new_store):
    s = new_store(seed=False)

    s.save_room(make_room())

    assert s.get_room("room-1") == make_room()


# --- Room plants -------------------------------------------------------------


# --- Areas -------------------------------------------------------------------


# --- Feed events -------------------------------------------------------------


def test_list_feed_events_is_newest_first_by_created_at(new_store):
    s = new_store(seed=False)
    s.save_feed_event(make_event("old", created_at=T0))
    s.save_feed_event(make_event("new", created_at=T0 + timedelta(hours=2)))
    s.save_feed_event(make_event("mid", created_at=T0 + timedelta(hours=1)))

    assert [e.id for e in s.list_feed_events("room-1")] == ["new", "mid", "old"]


# --- Follows -----------------------------------------------------------------


# --- Photos ------------------------------------------------------------------


# --- Transactions ------------------------------------------------------------


def test_transaction_rolls_back_every_save_and_delete_when_the_block_raises(new_store):
    s = new_store(seed=False)
    s.save_room(make_room("kept"))
    s.save_follow(make_follow())

    with pytest.raises(RuntimeError):
        with s.transaction():
            s.save_room(make_room("kept", name="Changed"))
            s.save_room(make_room("added"))
            s.delete_follow("f-1")
            with s.transaction():
                s.save_photo(make_photo())
            raise RuntimeError("boom")

    assert [(r.id, r.name) for r in s.list_rooms()] == [("kept", "Test room")]
    assert s.get_follow_by_token("tok-1") is not None
    assert s.get_photo("photo-1") is None


# --- Reset -------------------------------------------------------------------


# --- Encapsulation -----------------------------------------------------------


# --- SQLite persistence ------------------------------------------------------


def test_sqlite_store_keeps_data_across_a_restart_and_never_reseeds(tmp_path, monkeypatch):
    path = tmp_path / "fern.db"
    monkeypatch.setenv("FERNSLOP_DB_PATH", str(path))
    first = get_store()
    assert isinstance(first, SqliteStore) and path.exists()
    seeded_room = first.list_rooms()[0]
    first.save_room(seeded_room.model_copy(update={"name": "Edited"}))
    first.save_room(make_room("mine"))
    first.save_room_plant(make_room_plant(room_id="mine"))
    first.save_follow(make_follow(room_id="mine"))
    undo = {"kind": "delete_plant", "room_plant_id": "rp-1"}
    first.save_feed_event(make_event(room_id="mine", undo_payload=undo))
    first.save_photo(make_photo("5f0f2f6e-0000-4000-8000-000000000001", data=bytes(range(256))))
    first.delete_follow("f-1")
    first.save_follow(make_follow("f-2", room_id="mine", unsubscribe_token="tok-2"))

    reopened = SqliteStore(path)

    assert reopened.get_room(seeded_room.id).name == "Edited"
    assert len(reopened.list_rooms()) == 4
    assert reopened.get_room_plant("rp-1") == make_room_plant(room_id="mine")
    assert reopened.get_feed_event("ev-1").undo_payload.room_plant_id == "rp-1"
    assert [f.id for f in reopened.list_follows("mine")] == ["f-2"]
    client = TestClient(app)
    response = client.get("/api/photos/5f0f2f6e-0000-4000-8000-000000000001")
    assert response.content == bytes(range(256))
    reopened.reset()
    assert reopened.get_room(seeded_room.id).name == seeded_room.name
