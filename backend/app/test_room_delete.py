import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app import digest, live, room_purge, room_restore, timestamps
from app.main import app
from app.models import RoomArea
from app.sql_store import SqlStore
from app.store import get_store
from app.test_store import make_event, make_follow, make_photo

HEADERS = {"X-Device-Id": "device-1", "X-Actor-Name": "Tess"}
UNKNOWN_ID = "00000000-0000-4000-8000-000000000000"
NOT_FOUND = {"message": "Room not found"}
PHOTO_IDS = [f"00000000-0000-4000-8000-00000000000{n}" for n in (1, 2, 3)]


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


def make_area(room_id, **overrides) -> RoomArea:
    fields = {
        "id": "area-gone",
        "room_id": room_id,
        "label": "Old bed",
        "shape": "rect",
        "x_pct": 10,
        "y_pct": 10,
        "w_pct": 20,
        "h_pct": 20,
        "colour": "soil",
        "deleted_at": timestamps.now(),
    }
    return RoomArea(**{**fields, **overrides})


def post_with_photo(api, room_id, photo):
    response = api.post(f"/api/rooms/{room_id}/posts", json={"photo_id": photo.id}, headers=HEADERS)
    assert response.status_code == 201


# --- Delete ----------------------------------------------------------------


def test_delete_room_hides_the_room_from_the_api_but_keeps_all_its_data_after_a_restart(tmp_path):
    url = f"sqlite:///{tmp_path / 'fern.db'}"
    store = SqlStore(url)
    app.dependency_overrides[get_store] = lambda: store
    try:
        api = TestClient(app)
        room = store.list_rooms()[0]
        store.save_follow(make_follow(id="f-kept", room_id=room.id, unsubscribe_token="tok-kept"))
        kept = (store.list_room_plants(room.id), store.list_areas(room.id), store.list_feed_events(room.id))

        response = api.delete(f"/api/rooms/{room.id}")  # no actor headers

        assert (response.status_code, response.content) == (204, b"")
        assert api.get(f"/api/rooms/{room.id}").status_code == 404
        listed = api.get("/api/rooms").json()["rooms"]
        assert room.id not in [s["room"]["id"] for s in listed]
        assert all("deleted_at" not in s["room"] for s in listed)
        assert room.id not in {d.room_id for d in digest.build_digests(store, timestamps.now())}
        restarted = SqlStore(url)
        assert restarted.get_room(room.id) is None
        assert [r.id for r in restarted.list_deleted_rooms()] == [room.id]
        assert (
            restarted.list_room_plants(room.id),
            restarted.list_areas(room.id),
            restarted.list_feed_events(room.id),
        ) == kept
        assert [f.id for f in restarted.list_follows(room.id)] == ["f-kept"]
    finally:
        app.dependency_overrides.pop(get_store, None)


def test_delete_room_is_idempotent_and_later_calls_on_the_room_give_404(api, store, monkeypatch):
    closed = []
    monkeypatch.setattr(live, "close_room", closed.append)
    room_id = store.list_rooms()[0].id
    other_rooms = [r for r in store.list_rooms() if r.id != room_id]
    # The room's rows are kept by the soft delete, so their own endpoints must 404 too.
    room_plant = store.list_room_plants(room_id)[0]
    event = store.list_feed_events(room_id)[0]

    for delete_id in (room_id, room_id, UNKNOWN_ID, "not-a-uuid"):  # first, second, unknown, non-UUID
        response = api.delete(f"/api/rooms/{delete_id}")
        assert (response.status_code, response.content) == (204, b"")
        assert store.list_rooms() == other_rooms  # the repeats changed nothing
    assert closed == [room_id]  # only the delete that marked the room closes the streams
    calls = [
        api.get(f"/api/rooms/{room_id}"),
        api.post(f"/api/rooms/{room_id}/posts", json={"text": "hi"}, headers=HEADERS),
        api.post(f"/api/rooms/{room_id}/plants", json={"plant_id": store.list_plants()[0].id}, headers=HEADERS),
        api.post(f"/api/rooms/{room_id}/areas", json=make_area(room_id).model_dump(mode="json"), headers=HEADERS),
        api.post(f"/api/rooms/{room_id}/follows", json={"email": "ada@example.com"}),
        api.get(f"/api/rooms/{room_id}/live"),
    ]
    assert [(r.status_code, r.json()) for r in calls] == [(404, NOT_FOUND)] * len(calls)
    by_child = [
        api.patch(f"/api/room-plants/{room_plant.id}", json={"x_pct": 5, "y_pct": 5}, headers=HEADERS),
        api.post(f"/api/feed-events/{event.id}/undo", headers=HEADERS),
    ]
    assert [r.status_code for r in by_child] == [404] * len(by_child)


def test_delete_room_by_two_people_at_once_gives_both_204_marks_it_once_and_closes_streams_once(api, store, monkeypatch):
    closed = []
    monkeypatch.setattr(live, "close_room", closed.append)
    room_id = store.list_rooms()[0].id
    barrier = threading.Barrier(2)

    def delete_together():
        barrier.wait()
        return api.delete(f"/api/rooms/{room_id}").status_code

    with ThreadPoolExecutor(2) as pool:
        statuses = [f.result() for f in [pool.submit(delete_together) for _ in range(2)]]

    assert statuses == [204, 204]
    assert closed == [room_id]
    assert store.get_room(room_id) is None
    assert [r.id for r in store.list_deleted_rooms()] == [room_id]


# --- Live streams ------------------------------------------------------------


def test_delete_room_sends_open_streams_a_last_change_and_ends_them(api, store, monkeypatch):
    monkeypatch.setenv(live.PING_ENV, "60")
    room_id = store.list_rooms()[0].id

    async def scenario():
        stream = live.event_stream(room_id)
        assert await asyncio.wait_for(anext(stream), 2) == live.PING_FRAME
        assert live.subscriber_count(room_id) == 1

        response = await asyncio.to_thread(api.delete, f"/api/rooms/{room_id}")

        assert response.status_code == 204
        assert await asyncio.wait_for(anext(stream), 2) == f"event: change\ndata: {room_id}\n\n"
        with pytest.raises(StopAsyncIteration):
            await asyncio.wait_for(anext(stream), 2)

    asyncio.run(scenario())

    assert live.subscriber_count(room_id) == 0


# --- Purge and restore -------------------------------------------------------


def soft_delete(api, store, room_id, days_ago):
    """Delete through the API, then backdate the mark by ``days_ago`` days."""
    assert api.delete(f"/api/rooms/{room_id}").status_code == 204
    [room] = [r for r in store.list_deleted_rooms() if r.id == room_id]
    store.save_room(room.model_copy(update={"deleted_at": timestamps.now() - timedelta(days=days_ago)}))


def test_purge_removes_rooms_deleted_over_7_days_ago_with_their_data_and_keeps_younger_ones(
    api, store, monkeypatch, capsys
):
    monkeypatch.setattr(room_purge, "get_store", lambda: store)
    old, young, live_room = store.list_rooms()[:3]
    only_old, shared = make_photo(PHOTO_IDS[0]), make_photo(PHOTO_IDS[1])
    for photo in (only_old, shared):
        store.save_photo(photo)
    post_with_photo(api, old.id, only_old)
    post_with_photo(api, old.id, shared)
    # Posting a photo twice is refused (#199), but posts from before that can still share one.
    store.save_feed_event(make_event(id="ev-shared", room_id=young.id, photo_url=shared.url))
    store.save_follow(make_follow(id="f-old", room_id=old.id, unsubscribe_token="tok-old"))
    soft_delete(api, store, old.id, days_ago=8)
    soft_delete(api, store, young.id, days_ago=6)

    first = room_purge.main([])
    second = room_purge.main([])

    assert (first, second) == (0, 0)
    assert capsys.readouterr().out.splitlines() == ["Purged 1 room(s)", "Purged 0 room(s)"]
    assert [r.id for r in store.list_deleted_rooms()] == [young.id]
    assert store.list_room_plants(old.id, include_deleted=True) == []
    assert store.list_areas(old.id, include_deleted=True) == []
    assert store.list_feed_events(old.id) == []
    assert api.post("/api/follows/unsubscribe", json={"token": "tok-old"}).json() == {"unsubscribed": False}
    assert api.get(only_old.url).status_code == 404
    assert api.get(shared.url).status_code == 200  # the young deleted room's post still uses it
    assert store.list_feed_events(young.id) != []
    assert store.get_room(live_room.id) is not None


def test_restore_brings_a_deleted_room_back_with_its_data_and_rejects_live_or_unknown_ids(
    api, store, monkeypatch, capsys
):
    monkeypatch.setattr(room_restore, "get_store", lambda: store)
    room, live_room = store.list_rooms()[:2]
    store.save_follow(make_follow(id="f-back", room_id=room.id, unsubscribe_token="tok-back"))
    before = api.get(f"/api/rooms/{room.id}").json()
    soft_delete(api, store, room.id, days_ago=3)
    rooms_before = len(store.list_rooms())

    listed = room_restore.main(["--list"])
    restored = room_restore.main([room.id])
    refused = [room_restore.main([room.id]), room_restore.main([live_room.id]), room_restore.main([UNKNOWN_ID])]

    out = capsys.readouterr()
    assert (listed, restored, refused) == (0, 0, [1, 1, 1])
    assert out.out.splitlines()[0].startswith(f"{room.id}\t{room.name}\tdeleted at ")
    assert out.err.count("No deleted room with id") == 3
    assert api.get(f"/api/rooms/{room.id}").json() == before
    assert [f.id for f in store.list_follows(room.id)] == ["f-back"]
    assert [s["room"]["id"] for s in api.get("/api/rooms").json()["rooms"]].count(room.id) == 1
    assert len(store.list_rooms()) == rooms_before + 1  # a seed garden comes back once, never re-seeded
