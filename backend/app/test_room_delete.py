import asyncio

import pytest
from fastapi.testclient import TestClient

from app import digest, live, sql_store, timestamps
from app.main import app
from app.models import RoomArea
from app.sql_store import SqlStore
from app.store import get_store
from app.test_store import make_event, make_follow, make_photo, make_room_plant

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
    fields = dict(
        id="area-gone",
        room_id=room_id,
        label="Old bed",
        shape="rect",
        x_pct=10,
        y_pct=10,
        w_pct=20,
        h_pct=20,
        colour="soil",
        deleted_at=timestamps.now(),
    )
    return RoomArea(**{**fields, **overrides})


def post_with_photo(api, room_id, photo):
    response = api.post(f"/api/rooms/{room_id}/posts", json={"photo_id": photo.id}, headers=HEADERS)
    assert response.status_code == 201


# --- Delete ----------------------------------------------------------------


def test_delete_room_removes_the_room_and_all_its_data_and_keeps_it_gone_after_a_restart(tmp_path):
    url = f"sqlite:///{tmp_path / 'fern.db'}"
    store = SqlStore(url)
    app.dependency_overrides[get_store] = lambda: store
    try:
        api = TestClient(app)
        room, other = store.list_rooms()[:2]
        store.save_room_plant(make_room_plant(id="rp-gone", room_id=room.id, deleted_at=timestamps.now()))
        store.save_area(make_area(room.id))
        store.save_feed_event(make_event(id="ev-undone", room_id=room.id, undone_at=timestamps.now()))
        store.save_follow(make_follow(id="f-gone", room_id=room.id, unsubscribe_token="tok-gone"))
        plants_before = store.list_plants()

        response = api.delete(f"/api/rooms/{room.id}")  # no actor headers

        assert (response.status_code, response.content) == (204, b"")
        assert api.get(f"/api/rooms/{room.id}").status_code == 404
        assert [s["room"]["id"] for s in api.get("/api/rooms").json()].count(room.id) == 0
        assert store.list_room_plants(room.id, include_deleted=True) == []
        assert store.list_areas(room.id, include_deleted=True) == []
        assert store.list_feed_events(room.id) == []
        assert store.list_follows(room.id) == []
        assert api.post("/api/follows/unsubscribe", json={"token": "tok-gone"}).json() == {"unsubscribed": False}
        assert store.list_plants() == plants_before
        assert room.id not in {d.room_id for d in digest.build_digests(store, timestamps.now())}
        assert store.get_room(other.id) is not None

        restarted = SqlStore(url)
        assert restarted.get_room(room.id) is None
        assert len(restarted.list_rooms()) == 2
    finally:
        app.dependency_overrides.pop(get_store, None)


def test_delete_room_removes_photos_only_that_room_used_and_keeps_shared_and_unposted_ones(api, store):
    room, other = store.list_rooms()[:2]
    only_here, shared, unposted = make_photo(PHOTO_IDS[0]), make_photo(PHOTO_IDS[1]), make_photo(PHOTO_IDS[2])
    for photo in (only_here, shared, unposted):
        store.save_photo(photo)
    post_with_photo(api, room.id, only_here)
    post_with_photo(api, room.id, shared)
    post_with_photo(api, other.id, shared)

    assert api.delete(f"/api/rooms/{room.id}").status_code == 204

    assert api.get(only_here.url).status_code == 404
    assert api.get(shared.url).status_code == 200
    assert api.get(unposted.url).status_code == 200


def test_delete_room_unknown_twice_or_non_uuid_gives_404_and_later_calls_on_it_give_404(api, store):
    room_id = store.list_rooms()[0].id
    assert api.delete(f"/api/rooms/{room_id}").status_code == 204

    for bad_id in (room_id, UNKNOWN_ID, "not-a-uuid"):
        response = api.delete(f"/api/rooms/{bad_id}")
        assert (response.status_code, response.json()) == (404, NOT_FOUND)
    calls = [
        api.post(f"/api/rooms/{room_id}/posts", json={"text": "hi"}, headers=HEADERS),
        api.post(f"/api/rooms/{room_id}/plants", json={"plant_id": store.list_plants()[0].id}, headers=HEADERS),
        api.post(f"/api/rooms/{room_id}/areas", json=make_area(room_id).model_dump(mode="json"), headers=HEADERS),
        api.post(f"/api/rooms/{room_id}/follows", json={"email": "ada@example.com"}),
        api.get(f"/api/rooms/{room_id}/live"),
    ]
    assert [(r.status_code, r.json()) for r in calls] == [(404, NOT_FOUND)] * len(calls)


def test_delete_room_that_fails_midway_changes_nothing_and_does_not_close_streams(store, monkeypatch):
    api = TestClient(app, raise_server_exceptions=False)
    room = store.list_rooms()[0]
    before = (store.list_rooms(), store.list_room_plants(room.id), store.list_feed_events(room.id))
    assert any(e.photo_url for e in before[2])  # the photo step is the last one, after the rows are deleted
    closed = []
    monkeypatch.setattr(live, "close_room", closed.append)

    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(sql_store, "exists", boom)

    response = api.delete(f"/api/rooms/{room.id}")

    assert response.status_code == 500
    assert (store.list_rooms(), store.list_room_plants(room.id), store.list_feed_events(room.id)) == before
    assert closed == []


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
