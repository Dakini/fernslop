from datetime import UTC, datetime, timedelta

import pytest

from app.models import FeedEvent, Room, RoomPlant, StoredFollow, StoredPhoto
from app.sql_store import SqlStore

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


@pytest.fixture
def new_store():
    """A factory: ``new_store()`` is a seeded in-memory store, ``new_store(seed=False)`` an empty one."""
    return lambda seed=True: SqlStore("sqlite://", seed=seed)


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
