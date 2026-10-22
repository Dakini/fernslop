import asyncio
import contextlib
import io
import threading

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import live
from app.main import app
from app.routers.live import subscribe
from app.sql_store import SqlStore
from app.store import get_store

HEADERS = {"X-Device-Id": "device-1", "X-Actor-Name": "Tess"}
UNDO_HEADERS = {"X-Device-Id": "device-2", "X-Actor-Name": "Uma"}
PING = ": ping\n\n"


def change(room_id):
    return f"event: change\ndata: {room_id}\n\n"


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


@pytest.fixture(autouse=True)
def quiet_pings(monkeypatch):
    """Long ping interval unless a test sets its own, so frames are only what the test causes."""
    monkeypatch.setenv(live.PING_ENV, "60")


class Stream:
    """Drives ``live.event_stream`` on the running loop, as the response body would."""

    def __init__(self, room_id):
        self.generator = live.event_stream(room_id)
        self.pending = None

    async def frames(self, settle=0.15):
        """Every frame that arrives until nothing new shows up for ``settle`` seconds."""
        received = []
        while True:
            if self.pending is None:
                self.pending = asyncio.ensure_future(anext(self.generator))
            done, _ = await asyncio.wait({self.pending}, timeout=settle)
            if not done:
                return received
            received.append(self.pending.result())
            self.pending = None

    async def close(self):
        if self.pending is not None:
            self.pending.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.pending
        await self.generator.aclose()


async def opened(room_id):
    stream = Stream(room_id)
    assert await stream.frames() == [PING]
    return stream


def room_ids(store):
    first, second = store.list_rooms()[:2]
    return first.id, second.id


def test_stream_opens_with_a_ping_and_no_actor_headers_and_unknown_rooms_get_404(api, store):
    room_id = room_ids(store)[0]

    async def scenario():
        response = await subscribe(room_id, store)
        assert response.status_code == 200
        assert response.media_type == "text/event-stream"
        assert response.headers["cache-control"] == "no-cache"
        assert live.subscriber_count(room_id) == 0  # subscribes only once the stream runs
        assert await anext(response.body_iterator) == PING
        assert live.subscriber_count(room_id) == 1
        await response.body_iterator.aclose()

    asyncio.run(scenario())
    for bad_id in ("00000000-0000-4000-8000-000000000000", "not-a-uuid"):
        response = api.get(f"/api/rooms/{bad_id}/live")
        assert (response.status_code, response.json()) == (404, {"message": "Room not found"})
    assert live.subscriber_count() == 0


def test_notify_reaches_only_its_rooms_streams_from_any_thread_and_never_raises(store):
    room_id, other_id = room_ids(store)
    live.notify(room_id)  # no subscribers

    async def stale_subscriber():
        return live._subscribe(room_id)  # its loop closes when asyncio.run returns

    stale = asyncio.run(stale_subscriber())
    live.notify(room_id)  # a stream whose loop has closed
    live._unsubscribe(stale)

    async def scenario():
        first, second, elsewhere = await opened(room_id), await opened(room_id), await opened(other_id)
        thread = threading.Thread(target=live.notify, args=(room_id,))
        thread.start()
        thread.join()
        results = [await s.frames() for s in (first, second, elsewhere)]
        live.notify(room_id)
        live.notify(room_id)  # unread notifies may merge, but one is always sent
        merged = await first.frames()
        for stream in (first, second, elsewhere):
            await stream.close()
        return results, merged

    results, merged = asyncio.run(scenario())

    assert results == [[change(room_id)], [change(room_id)], []]
    assert merged == [change(room_id)]


def test_pings_repeat_at_the_configured_interval_and_bad_values_fall_back_to_25(store, monkeypatch):
    monkeypatch.setenv(live.PING_ENV, "0.02")

    async def scenario():
        generator = live.event_stream(room_ids(store)[0])
        frames = [await asyncio.wait_for(anext(generator), 2) for _ in range(3)]
        await generator.aclose()
        return frames

    assert asyncio.run(scenario()) == [PING] * 3
    for bad in ("", "soon", "0", "-5"):
        monkeypatch.setenv(live.PING_ENV, bad)
        assert live.ping_seconds() == 25
    monkeypatch.delenv(live.PING_ENV)
    assert live.ping_seconds() == 25


def test_subscribers_are_removed_when_streams_close_or_are_cancelled(store):
    room_id, other_id = room_ids(store)

    async def scenario():
        for _ in range(3):
            await (await opened(room_id)).close()
        kept = await opened(other_id)
        doomed = await opened(room_id)
        counts = (live.subscriber_count(room_id), live.subscriber_count(other_id), live.subscriber_count())
        task = doomed.pending  # the stream is waiting for its next frame
        task.cancel()  # cancelled mid-stream, as when a client disconnects
        with contextlib.suppress(asyncio.CancelledError):
            await task
        after_cancel = live.subscriber_count(room_id)
        await kept.close()
        return counts, after_cancel

    counts, after_cancel = asyncio.run(scenario())

    assert counts == (1, 1, 2)
    assert after_cancel == 0
    assert live.subscriber_count() == 0


def area_payload():
    return {"label": "Bed", "shape": "rect", "x_pct": 10, "y_pct": 20, "w_pct": 30, "h_pct": 40, "colour": "soil"}


def test_each_successful_mutation_gives_one_change_and_other_requests_give_none(api, store):
    room_id, other_id = room_ids(store)
    tomato = next(p.id for p in store.list_plants() if p.common_name == "Tomato")
    plant = next(rp for rp in store.list_room_plants(room_id) if rp.plant_id == tomato)
    jpeg = io.BytesIO()
    Image.new("RGB", (2, 2)).save(jpeg, "JPEG")
    jpeg = jpeg.getvalue()

    def quiet_requests():
        api.post("/api/rooms", json={"name": "New"})
        api.post(f"/api/rooms/{room_id}/follows", json={"email": "ada@example.com"})
        token = store.get_follow_by_email(room_id, "ada@example.com").unsubscribe_token
        api.post("/api/follows/unsubscribe", json={"token": token})
        api.post("/api/photos", files={"file": ("p.jpg", jpeg, "image/jpeg")})
        api.get(f"/api/rooms/{room_id}")
        api.get("/api/rooms")
        assert api.post(f"/api/rooms/{room_id}/plants", json={}, headers=HEADERS).status_code == 400

    async def scenario():
        stream, elsewhere = await opened(room_id), await opened(other_id)
        seen = []

        async def mutate(method, path, **kwargs):
            response = await asyncio.to_thread(getattr(api, method), f"/api{path}", headers=HEADERS, **kwargs)
            assert response.status_code < 300, response.text
            seen.append(await stream.frames())
            return response

        added = (await mutate("post", f"/rooms/{room_id}/plants", json={"plant_id": tomato})).json()
        await mutate("patch", f"/room-plants/{added['id']}", json={"x_pct": 5, "y_pct": 6})
        await mutate("post", f"/room-plants/{plant.id}/care", json={"care": "water"})
        await mutate("delete", f"/room-plants/{added['id']}")
        area = (await mutate("post", f"/rooms/{room_id}/areas", json=area_payload())).json()
        await mutate("patch", f"/areas/{area['id']}", json={"label": "Renamed"})
        await mutate("delete", f"/areas/{area['id']}")
        undo_id = store.list_feed_events(room_id)[0].id  # the area removal
        undone = await asyncio.to_thread(api.post, f"/api/feed-events/{undo_id}/undo", headers=UNDO_HEADERS)
        assert undone.status_code == 204
        seen.append(await stream.frames())
        await mutate("post", f"/rooms/{room_id}/posts", json={"text": "Hello", "photo_id": None})
        await asyncio.to_thread(quiet_requests)
        seen.append(await stream.frames())
        other_frames = await elsewhere.frames()
        await stream.close()
        await elsewhere.close()
        return seen, other_frames

    seen, other_frames = asyncio.run(scenario())

    assert seen == [[change(room_id)]] * 9 + [[]]
    assert other_frames == []
