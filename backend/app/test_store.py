import re
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.models import (
    FeedEvent,
    Room,
    RoomArea,
    RoomFollow,
    RoomPlant,
    StoredFollow,
    StoredPhoto,
)
from app.store import Store, StoreProtocol, get_store, store

T0 = datetime(2026, 10, 22, 9, 30, 0, tzinfo=UTC)

PROTOCOL_METHODS = [
    "list_plants",
    "get_plant",
    "list_rooms",
    "get_room",
    "save_room",
    "list_room_plants",
    "get_room_plant",
    "save_room_plant",
    "list_areas",
    "get_area",
    "save_area",
    "list_feed_events",
    "get_feed_event",
    "save_feed_event",
    "list_follows",
    "get_follow_by_email",
    "get_follow_by_token",
    "save_follow",
    "delete_follow",
    "get_photo",
    "save_photo",
    "transaction",
    "reset",
]


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


def make_area(id="area-1", room_id="room-1", **overrides) -> RoomArea:
    fields = dict(
        id=id, room_id=room_id, label="Bed", shape="rect", x_pct=1, y_pct=2, w_pct=3, h_pct=4, colour="soil",
        deleted_at=None,
    )
    return RoomArea(**{**fields, **overrides})


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


def empty_store() -> Store:
    return Store(seed=False)


# --- Protocol and construction -----------------------------------------------


def test_store_implements_the_store_protocol():
    assert isinstance(Store(), StoreProtocol)
    assert isinstance(empty_store(), StoreProtocol)


def test_store_protocol_declares_exactly_the_documented_methods():
    declared = {name for name in vars(StoreProtocol) if not name.startswith("_")}

    assert declared == set(PROTOCOL_METHODS)


def test_get_store_returns_the_module_level_store():
    assert get_store() is store


def test_store_built_with_seed_has_the_seed():
    fresh = Store()

    assert len(fresh.list_plants()) == 51
    assert len(fresh.list_rooms()) == 3


def test_store_built_without_seed_is_empty():
    fresh = empty_store()

    assert fresh.list_plants() == []
    assert fresh.list_rooms() == []
    assert fresh.get_photo("anything") is None


def test_store_without_seed_stays_empty_after_reset():
    fresh = empty_store()
    fresh.save_room(make_room())

    fresh.reset()

    assert fresh.list_rooms() == []
    assert fresh.list_plants() == []


def test_empty_store_can_be_injected_with_a_dependency_override():
    app = FastAPI()

    @app.get("/throwaway")
    def throwaway(s: StoreProtocol = Depends(get_store)):
        return {"rooms": len(s.list_rooms()), "plants": len(s.list_plants())}

    seeded = TestClient(app).get("/throwaway").json()
    app.dependency_overrides[get_store] = empty_store
    injected = TestClient(app).get("/throwaway").json()

    assert seeded == {"rooms": 3, "plants": 51}
    assert injected == {"rooms": 0, "plants": 0}


# --- Plants ------------------------------------------------------------------


def test_list_plants_keeps_the_seed_order():
    plants = Store().list_plants()

    assert plants[0].id == "plant-basil"
    assert plants[10].id == "plant-tomato"
    assert plants[-1].id == "plant-japanese-maple"


def test_get_plant_returns_the_plant_or_none():
    s = Store()

    assert s.get_plant("plant-tomato").common_name == "Tomato"
    assert s.get_plant("plant-nope") is None
    assert s.get_plant("") is None
    assert s.get_plant("not-a-uuid") is None


def test_plants_are_copies_so_mutating_one_does_not_change_the_store():
    s = Store()

    s.get_plant("plant-tomato").common_name = "Changed"
    s.list_plants()[0].common_name = "Changed"

    assert s.get_plant("plant-tomato").common_name == "Tomato"
    assert s.list_plants()[0].common_name == "Basil"


# --- Rooms -------------------------------------------------------------------


def test_save_room_inserts_and_get_room_returns_it():
    s = empty_store()

    s.save_room(make_room())

    assert s.get_room("room-1") == make_room()


def test_save_room_with_an_existing_id_replaces_it_in_place():
    s = empty_store()
    s.save_room(make_room("a"))
    s.save_room(make_room("b"))

    s.save_room(make_room("a", name="Renamed"))

    assert [r.id for r in s.list_rooms()] == ["a", "b"]
    assert s.get_room("a").name == "Renamed"


def test_list_rooms_returns_insertion_order():
    s = empty_store()
    for room_id in ["c", "a", "b"]:
        s.save_room(make_room(room_id))

    assert [r.id for r in s.list_rooms()] == ["c", "a", "b"]


def test_get_room_with_unknown_ids_returns_none():
    s = empty_store()

    assert s.get_room("missing") is None
    assert s.get_room("") is None
    assert s.get_room("not-a-uuid") is None


def test_fetched_room_is_a_copy_so_renaming_it_does_not_change_the_store():
    s = empty_store()
    s.save_room(make_room(name="Original"))

    fetched = s.get_room("room-1")
    fetched.name = "Changed"

    assert s.get_room("room-1").name == "Original"


def test_listed_rooms_are_copies():
    s = empty_store()
    s.save_room(make_room(name="Original"))

    s.list_rooms()[0].name = "Changed"

    assert s.get_room("room-1").name == "Original"


def test_room_mutated_after_save_does_not_change_the_stored_record():
    s = empty_store()
    room = make_room(name="Original")
    s.save_room(room)

    room.name = "Changed"

    assert s.get_room("room-1").name == "Original"


# --- Room plants -------------------------------------------------------------


def test_save_room_plant_inserts_replaces_in_place_and_keeps_listing_order():
    s = empty_store()
    s.save_room_plant(make_room_plant("a"))
    s.save_room_plant(make_room_plant("b"))

    s.save_room_plant(make_room_plant("a", x_pct=99))

    assert [p.id for p in s.list_room_plants("room-1")] == ["a", "b"]
    assert s.get_room_plant("a").x_pct == 99


def test_list_room_plants_only_returns_plants_of_that_room():
    s = empty_store()
    s.save_room_plant(make_room_plant("a", room_id="room-1"))
    s.save_room_plant(make_room_plant("b", room_id="room-2"))

    assert [p.id for p in s.list_room_plants("room-2")] == ["b"]


def test_list_room_plants_leaves_out_soft_deleted_unless_asked():
    s = empty_store()
    s.save_room_plant(make_room_plant("live"))
    s.save_room_plant(make_room_plant("gone", deleted_at=T0))

    assert [p.id for p in s.list_room_plants("room-1")] == ["live"]
    assert [p.id for p in s.list_room_plants("room-1", include_deleted=True)] == ["live", "gone"]


def test_get_room_plant_returns_soft_deleted_rows():
    s = empty_store()
    s.save_room_plant(make_room_plant("gone", deleted_at=T0))

    assert s.get_room_plant("gone").deleted_at == T0


def test_room_plant_unknown_ids_and_rooms_return_none_and_empty_lists():
    s = empty_store()

    assert s.get_room_plant("missing") is None
    assert s.get_room_plant("") is None
    assert s.get_room_plant("not-a-uuid") is None
    assert s.list_room_plants("missing-room") == []
    assert s.list_room_plants("missing-room", include_deleted=True) == []


def test_room_plants_are_copies_in_both_directions():
    s = empty_store()
    plant = make_room_plant()
    s.save_room_plant(plant)

    plant.x_pct = 50
    s.get_room_plant("rp-1").x_pct = 60
    s.list_room_plants("room-1")[0].x_pct = 70

    assert s.get_room_plant("rp-1").x_pct == 10


# --- Areas -------------------------------------------------------------------


def test_save_area_inserts_replaces_in_place_and_keeps_listing_order():
    s = empty_store()
    s.save_area(make_area("a"))
    s.save_area(make_area("b"))

    s.save_area(make_area("a", label="Renamed"))

    assert [a.id for a in s.list_areas("room-1")] == ["a", "b"]
    assert s.get_area("a").label == "Renamed"


def test_list_areas_leaves_out_soft_deleted_unless_asked():
    s = empty_store()
    s.save_area(make_area("live"))
    s.save_area(make_area("gone", deleted_at=T0))

    assert [a.id for a in s.list_areas("room-1")] == ["live"]
    assert [a.id for a in s.list_areas("room-1", include_deleted=True)] == ["live", "gone"]


def test_get_area_returns_soft_deleted_rows():
    s = empty_store()
    s.save_area(make_area("gone", deleted_at=T0))

    assert s.get_area("gone").deleted_at == T0


def test_area_unknown_ids_and_rooms_return_none_and_empty_lists():
    s = empty_store()

    assert s.get_area("missing") is None
    assert s.get_area("") is None
    assert s.get_area("not-a-uuid") is None
    assert s.list_areas("missing-room") == []


def test_areas_are_copies_in_both_directions():
    s = empty_store()
    area = make_area()
    s.save_area(area)

    area.label = "Changed"
    s.get_area("area-1").label = "Changed"
    s.list_areas("room-1")[0].label = "Changed"

    assert s.get_area("area-1").label == "Bed"


# --- Feed events -------------------------------------------------------------


def test_save_feed_event_inserts_and_get_feed_event_returns_it():
    s = empty_store()

    s.save_feed_event(make_event())

    assert s.get_feed_event("ev-1") == make_event()


def test_list_feed_events_is_newest_first_by_created_at():
    s = empty_store()
    s.save_feed_event(make_event("old", created_at=T0))
    s.save_feed_event(make_event("new", created_at=T0 + timedelta(hours=2)))
    s.save_feed_event(make_event("mid", created_at=T0 + timedelta(hours=1)))

    assert [e.id for e in s.list_feed_events("room-1")] == ["new", "mid", "old"]


def test_list_feed_events_puts_later_saved_first_when_timestamps_match():
    s = empty_store()
    for event_id in ["first", "second", "third"]:
        s.save_feed_event(make_event(event_id, created_at=T0))

    assert [e.id for e in s.list_feed_events("room-1")] == ["third", "second", "first"]


def test_list_feed_events_includes_undone_events():
    s = empty_store()
    s.save_feed_event(make_event("undone", undone_at=T0))

    assert [e.id for e in s.list_feed_events("room-1")] == ["undone"]


def test_replacing_a_feed_event_keeps_its_position():
    s = empty_store()
    s.save_feed_event(make_event("a", created_at=T0))
    s.save_feed_event(make_event("b", created_at=T0))

    s.save_feed_event(make_event("a", created_at=T0, undone_at=T0))

    assert [e.id for e in s.list_feed_events("room-1")] == ["b", "a"]
    assert s.get_feed_event("a").undone_at == T0


def test_list_feed_events_only_returns_events_of_that_room():
    s = empty_store()
    s.save_feed_event(make_event("a", room_id="room-1"))
    s.save_feed_event(make_event("b", room_id="room-2"))

    assert [e.id for e in s.list_feed_events("room-2")] == ["b"]


def test_feed_event_unknown_ids_and_rooms_return_none_and_empty_lists():
    s = empty_store()

    assert s.get_feed_event("missing") is None
    assert s.get_feed_event("") is None
    assert s.get_feed_event("not-a-uuid") is None
    assert s.list_feed_events("missing-room") == []


def test_feed_events_are_copies_in_both_directions():
    s = empty_store()
    event = make_event()
    s.save_feed_event(event)

    event.text = "Changed"
    s.get_feed_event("ev-1").text = "Changed"
    s.list_feed_events("room-1")[0].text = "Changed"

    assert s.get_feed_event("ev-1").text == "hello"


# --- Follows -----------------------------------------------------------------


def test_save_follow_inserts_and_replaces_in_place():
    s = empty_store()
    s.save_follow(make_follow("a", email="a@example.com", unsubscribe_token="t-a"))
    s.save_follow(make_follow("b", email="b@example.com", unsubscribe_token="t-b"))

    s.save_follow(make_follow("a", email="new@example.com", unsubscribe_token="t-a"))

    assert [f.email for f in s.list_follows("room-1")] == ["new@example.com", "b@example.com"]


def test_get_follow_by_email_is_case_insensitive():
    s = empty_store()
    s.save_follow(make_follow(email="Mixed.Case@Example.com"))

    assert s.get_follow_by_email("room-1", "mixed.case@example.COM").id == "f-1"


def test_get_follow_by_email_is_scoped_to_the_room():
    s = empty_store()
    s.save_follow(make_follow())

    assert s.get_follow_by_email("room-2", "a@example.com") is None
    assert s.get_follow_by_email("room-1", "other@example.com") is None


def test_get_follow_by_token_finds_the_follow_in_any_room():
    s = empty_store()
    s.save_follow(make_follow("f-1", room_id="room-1", unsubscribe_token="tok-1"))
    s.save_follow(make_follow("f-2", room_id="room-2", unsubscribe_token="tok-2"))

    assert s.get_follow_by_token("tok-2").id == "f-2"
    assert s.get_follow_by_token("nope") is None
    assert s.get_follow_by_token("") is None


def test_delete_follow_removes_it_and_reports_whether_it_existed():
    s = empty_store()
    s.save_follow(make_follow())

    first = s.delete_follow("f-1")
    second = s.delete_follow("f-1")

    assert (first, second) == (True, False)
    assert s.list_follows("room-1") == []
    assert s.get_follow_by_token("tok-1") is None


def test_list_follows_for_an_unknown_room_is_empty():
    assert empty_store().list_follows("missing-room") == []


def test_follows_are_copies_in_both_directions():
    s = empty_store()
    follow = make_follow()
    s.save_follow(follow)

    follow.email = "changed@example.com"
    s.list_follows("room-1")[0].email = "changed@example.com"

    assert s.get_follow_by_token("tok-1").email == "a@example.com"


def test_stored_follow_dumped_as_public_follow_leaves_the_token_out():
    public = make_follow().to_public()

    assert type(public) is RoomFollow
    assert public.model_dump(mode="json") == {
        "id": "f-1",
        "room_id": "room-1",
        "email": "a@example.com",
        "created_at": "2026-10-22T09:30:00.000Z",
    }


def test_room_follow_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        RoomFollow(id="f", room_id="r", email="a@example.com", created_at=T0, unsubscribe_token="leak")


# --- Photos ------------------------------------------------------------------


def test_save_photo_inserts_and_replaces_by_id():
    s = empty_store()
    s.save_photo(make_photo())

    s.save_photo(make_photo(data=b"new bytes"))

    assert s.get_photo("photo-1").data == b"new bytes"


def test_get_photo_with_unknown_ids_returns_none():
    s = empty_store()

    assert s.get_photo("missing") is None
    assert s.get_photo("") is None
    assert s.get_photo("not-a-uuid") is None


def test_seeded_photo_is_available_by_id():
    s = Store()
    photo_id = s.list_feed_events(s.list_rooms()[0].id)[0].photo_url.rsplit("/", 1)[1]

    assert s.get_photo(photo_id).content_type == "image/png"


def test_photos_are_copies():
    s = empty_store()
    photo = make_photo()
    s.save_photo(photo)

    photo.content_type = "image/jpeg"
    s.get_photo("photo-1").content_type = "image/jpeg"

    assert s.get_photo("photo-1").content_type == "image/png"


# --- Transactions ------------------------------------------------------------


def test_nested_transactions_in_one_thread_do_not_deadlock():
    s = empty_store()

    with s.transaction():
        with s.transaction():
            s.save_room(make_room())

    assert s.get_room("room-1") is not None


def test_transaction_does_not_roll_back_when_the_block_raises():
    s = empty_store()

    try:
        with s.transaction():
            s.save_room(make_room())
            raise RuntimeError("boom")
    except RuntimeError:
        pass

    assert s.get_room("room-1") is not None


def test_two_threads_cannot_be_inside_a_transaction_at_once():
    s = empty_store()
    inside = threading.Event()
    release = threading.Event()
    entered_second = threading.Event()

    def holder():
        with s.transaction():
            inside.set()
            release.wait(timeout=5)

    def waiter():
        with s.transaction():
            entered_second.set()

    first = threading.Thread(target=holder)
    first.start()
    inside.wait(timeout=5)
    second = threading.Thread(target=waiter)
    second.start()

    blocked = not entered_second.wait(timeout=0.2)
    release.set()
    first.join(timeout=5)
    second.join(timeout=5)

    assert blocked
    assert entered_second.is_set()


def test_reset_waits_for_a_transaction_held_by_another_thread():
    s = Store()
    inside = threading.Event()
    release = threading.Event()
    reset_done = threading.Event()

    def holder():
        with s.transaction():
            inside.set()
            release.wait(timeout=5)

    def resetter():
        s.reset()
        reset_done.set()

    first = threading.Thread(target=holder)
    first.start()
    inside.wait(timeout=5)
    second = threading.Thread(target=resetter)
    second.start()

    blocked = not reset_done.wait(timeout=0.2)
    release.set()
    first.join(timeout=5)
    second.join(timeout=5)

    assert blocked
    assert reset_done.is_set()


# --- Reset -------------------------------------------------------------------


def test_reset_restores_the_seed_after_changes():
    s = Store()
    seeded_rooms = [r.id for r in s.list_rooms()]
    live_counts = {rid: len(s.list_room_plants(rid)) for rid in seeded_rooms}
    first_room = seeded_rooms[0]
    tomato = s.list_room_plants(first_room)[0]
    s.save_room(make_room("extra"))
    s.save_room_plant(tomato.model_copy(update={"deleted_at": T0}))
    s.save_follow(make_follow(room_id=first_room))

    s.reset()

    assert [r.id for r in s.list_rooms()] == seeded_rooms
    assert {rid: len(s.list_room_plants(rid)) for rid in seeded_rooms} == live_counts
    assert s.get_room("extra") is None
    assert s.list_follows(first_room) == []
    assert s.get_follow_by_token("tok-1") is None


def test_reset_can_be_called_repeatedly():
    s = Store()
    ids = [r.id for r in s.list_rooms()]

    for _ in range(3):
        s.save_room(make_room("extra"))
        s.reset()

    assert [r.id for r in s.list_rooms()] == ids


def test_reset_keeps_room_ids_and_event_ids_identical():
    s = Store()
    room_id = s.list_rooms()[0].id
    event_ids = [e.id for e in s.list_feed_events(room_id)]

    s.reset()

    assert s.list_rooms()[0].id == room_id
    assert [e.id for e in s.list_feed_events(room_id)] == event_ids


def test_reset_restores_the_plant_table_without_reading_files(monkeypatch):
    s = Store()

    def no_files(*args, **kwargs):
        raise AssertionError("reset must not read files")

    monkeypatch.setattr("builtins.open", no_files)

    s.reset()

    assert len(s.list_plants()) == 51


def test_seeded_feed_events_list_newest_first():
    s = Store()
    room_id = s.list_rooms()[0].id

    stamps = [e.created_at for e in s.list_feed_events(room_id)]

    assert stamps == sorted(stamps, reverse=True)
    assert s.list_feed_events(room_id)[0].type == "post"


def test_seeded_soft_deleted_rows_are_hidden_from_default_listings():
    s = Store()
    elm, balcony = s.list_rooms()[0], s.list_rooms()[1]

    assert len(s.list_room_plants(elm.id)) == 4
    assert len(s.list_room_plants(elm.id, include_deleted=True)) == 5
    assert len(s.list_areas(balcony.id)) == 1
    assert len(s.list_areas(balcony.id, include_deleted=True)) == 2


# --- Encapsulation -----------------------------------------------------------


def test_nothing_outside_store_and_seed_reaches_into_the_stores_internals():
    app_dir = Path(__file__).parent
    pattern = re.compile(r"\bstore\._\w+|\bs\._\w+")
    offenders = []
    for path in app_dir.rglob("*.py"):
        if path.name in {"store.py", "seed.py", "test_store.py"}:
            continue
        for number, line in enumerate(path.read_text().splitlines(), start=1):
            if pattern.search(line):
                offenders.append(f"{path.name}:{number}")

    assert offenders == []
