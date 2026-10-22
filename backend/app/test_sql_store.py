import threading

from fastapi.testclient import TestClient

from app.main import app
from app.sql_store import SqlStore
from app.store import DATABASE_URL_ENV, DEFAULT_DATABASE_URL, close_stores, get_store
from app.test_store import (
    T0,
    make_event,
    make_follow,
    make_photo,
    make_room,
    make_room_plant,
)
from conftest import TEST_DATABASE_URL, requires_postgres

# Behaviour shared by every store lives in test_store.py; these cover what the SQL store adds.


# --- Configured database -----------------------------------------------------


def test_get_store_without_a_url_uses_a_fernslop_db_file_in_the_working_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(DATABASE_URL_ENV, raising=False)

    store = get_store()

    assert DEFAULT_DATABASE_URL == "sqlite:///fernslop.db"
    assert isinstance(store, SqlStore) and (tmp_path / "fernslop.db").exists()
    assert get_store() is store


def test_store_on_a_database_url_keeps_data_across_a_restart_and_never_reseeds(tmp_path, monkeypatch):
    path = tmp_path / "fern.db"
    monkeypatch.setenv(DATABASE_URL_ENV, f"sqlite:///{path}")
    first = get_store()
    assert path.exists()
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

    close_stores()
    reopened = get_store()

    assert reopened is not first
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


# --- Ordering and lookups ------------------------------------------------------


def test_replacing_a_record_keeps_its_position_and_equal_timestamps_list_the_later_saved_first():
    s = SqlStore("sqlite://", seed=False)
    s.save_room(make_room("a"))
    s.save_room(make_room("b"))
    s.save_room(make_room("a", name="Renamed"))
    s.save_feed_event(make_event("first", created_at=T0))
    s.save_feed_event(make_event("second", created_at=T0))
    s.save_feed_event(make_event("first", created_at=T0, text="Edited"))

    assert [(r.id, r.name) for r in s.list_rooms()] == [("a", "Renamed"), ("b", "Test room")]
    assert [e.id for e in s.list_feed_events("room-1")] == ["second", "first"]


def test_follow_lookup_by_email_ignores_case():
    s = SqlStore("sqlite://", seed=False)
    s.save_follow(make_follow(email="Ada@Example.com"))

    assert s.get_follow_by_email("room-1", "ADA@example.COM").id == "f-1"
    assert s.get_follow_by_email("room-2", "ada@example.com") is None


# --- Threads -------------------------------------------------------------------


def test_twenty_threads_each_reading_the_count_and_saving_in_a_transaction_end_with_twenty_records(tmp_path):
    s = SqlStore(f"sqlite:///{tmp_path / 'threads.db'}", seed=False)
    errors = []

    def add_one(number):
        try:
            with s.transaction():
                count = len(s.list_rooms())
                s.save_room(make_room(f"room-{number}", name=str(count)))
        except Exception as error:  # noqa: BLE001 - e.g. "database is locked"
            errors.append(error)

    threads = [threading.Thread(target=add_one, args=(n,)) for n in range(20)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert sorted(int(room.name) for room in s.list_rooms()) == list(range(20))


# --- Postgres (skipped unless FERNSLOP_TEST_DATABASE_URL is set) -----------------


@requires_postgres
def test_two_stores_starting_at_the_same_moment_on_an_empty_postgres_seed_it_once():
    stores, errors = [], []
    barrier = threading.Barrier(2)

    def start():
        try:
            barrier.wait()
            stores.append(SqlStore(TEST_DATABASE_URL))
        except Exception as error:  # noqa: BLE001 - report any failure from the thread
            errors.append(error)

    threads = [threading.Thread(target=start) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    restarted = SqlStore(TEST_DATABASE_URL)

    assert errors == []
    assert [len(s.list_rooms()) for s in (*stores, restarted)] == [3, 3, 3]
    assert len(restarted.list_plants()) == 51
    for s in (*stores, restarted):
        s.dispose()


@requires_postgres
def test_ten_threads_on_each_of_two_postgres_stores_reading_the_count_and_saving_end_with_twenty_records():
    stores = [SqlStore(TEST_DATABASE_URL, seed=False), SqlStore(TEST_DATABASE_URL, seed=False)]
    errors = []

    def add_one(number):
        s = stores[number % 2]  # separate stores: only the database can keep them exclusive
        try:
            with s.transaction():
                count = len(s.list_rooms())
                s.save_room(make_room(f"room-{number}", name=str(count)))
        except Exception as error:  # noqa: BLE001 - report any failure from the thread
            errors.append(error)

    threads = [threading.Thread(target=add_one, args=(n,)) for n in range(20)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert sorted(int(room.name) for room in stores[0].list_rooms()) == list(range(20))
    for s in stores:
        s.dispose()
