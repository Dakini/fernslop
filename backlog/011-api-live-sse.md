# [api] Live updates via Server-Sent Events

## Goal
`GET /api/rooms/{roomId}/live` (`subscribe` in `openapi.yaml`) streams a `change` message to every open stream of a room after each mutation in it, and `live.notify(room_id)` from [#006](006-api-room-plants.md) is made real. Implement after 006, 007, 008 and 009, so every mutation already calls `notify`.

## Acceptance criteria
- [ ] A seeded room answers 200 `text/event-stream` with `Cache-Control: no-cache` and no actor headers (EventSource cannot send them); the stream opens with a `: ping` line. An unknown or non-UUID id gives plain 404 `Room not found` (JSON, never 422) and subscribes nobody.
- [ ] `live.notify(room_id)` sends exactly `event: change\ndata: <roomId>\n\n` to every open stream of that room and to no stream of another room. Notifies a stream has not yet read may merge into one message, but one is always sent.
- [ ] `notify` is sync and is called from a plain thread (as route handlers run) while streams run on the event loop: the message arrives, it never blocks or raises, also with no subscribers or a stream whose loop has closed.
- [ ] A `: ping\n\n` line is sent every `FERNSLOP_SSE_PING_SECONDS` seconds (default 25; unset, non-numeric or <= 0 gives 25), read when a stream opens; pings never send a `change`.
- [ ] When a stream ends (client disconnect, cancellation, error) its subscriber is removed. `live.subscriber_count(room_id: str | None = None) -> int` counts open ones (all rooms if `None`) and is 0 after repeated connect and disconnect cycles.
- [ ] Through HTTP with a real subscriber, one successful add/move/remove/care, area add/update/delete, undo and post each gives one `change` for its own room. Room create, follow, unsubscribe, photo upload, reads and every 4xx give none.
- [ ] `uv run pytest` passes with tests per criterion; none opens an endless stream through `TestClient` (drive the async event generator, e.g. with `asyncio.run`, and use a tiny ping interval via `monkeypatch.setenv`).

## Out of scope
- Following does not notify: [#010](010-api-follows.md). Browser `EventSource` use: [#014](014-api-frontend-wiring.md). Fan-out across several workers or processes (this is one process): [#090](090-api-live-multi-worker.md).

## Constraints
- Code in `backend/app/live.py` (keep `notify(room_id: str) -> None`) and `routers/live.py` (registered in `routers/__init__.py`); tests in `backend/app/test_live.py`. SSE via Starlette `StreamingResponse` over an async generator; no new dependencies. Subscribe when the generator first runs and unsubscribe in `finally`.
- Hand-off: each subscriber owns an `asyncio.Queue` and the loop it was created on, kept under a `threading.Lock`; `notify` only calls `loop.call_soon_threadsafe(...)`, never touches asyncio objects directly. The route is `async def`, uses `Depends(get_store)` for the 404 and raises `ApiError`.

## Original request
**What:** `GET /rooms/{roomId}/live` is a `text/event-stream` that sends `event: change` / `data: <roomId>` after every mutation in that room, plus a `: ping` comment roughly every 25 s. **Why:** It keeps multiple browsers on the same room in sync.
**Edge cases:** It broadcasts on every mutation from 004 to 009, including undo, but not on follow or room creation. An unknown room returns 404 before the stream opens. Subscribers must be cleaned up on disconnect so they don't leak. Each room gets only its own events. Testing a stream with TestClient is awkward, so expose a way to inspect the broadcaster or keep the ping interval configurable for tests.

## Comments

- Engineer: implemented `live.py` (per-stream subscriber with an `asyncio.Queue(maxsize=1)` and its loop under a `threading.Lock`; `notify` only calls `call_soon_threadsafe`; `subscriber_count`; `event_stream` async generator with `FERNSLOP_SSE_PING_SECONDS` pings) and `routers/live.py` (`subscribe`, 404 via `ApiError` before streaming, registered in `routers/__init__.py`). 5 tests in `backend/app/test_live.py`, all passing; the full suite passes except `test_store.py::test_transaction_does_not_roll_back_when_the_block_raises`, which comes from the in-progress SQLite store work (issue 015), not this change. No acceptance criteria changed.

## QA: PASS

- [x] Seeded room gives 200 `text/event-stream`, `Cache-Control: no-cache`, no actor headers, opens with `: ping`; unknown and non-UUID ids give JSON 404 `Room not found` - PASS (real uvicorn + httpx)
- [x] `notify` sends exactly `event: change\ndata: <roomId>\n\n` to the room's streams and none to another room's - PASS (real add-plant gave one change on its room, nothing on the other room)
- [x] `notify` is sync, uses `call_soon_threadsafe`, tolerates no subscribers / closed loop; message arrived from a route-handler thread - PASS
- [x] `: ping` every `FERNSLOP_SSE_PING_SECONDS`, never a `change` - PASS (set to 1: pings at ~1 s; default/invalid handling read in `ping_seconds`)
- [x] Subscriber removed when a stream ends; `subscriber_count` is 0 after connect/disconnect/cancel cycles - PASS (covered by `test_live.py`)
- [x] One `change` per successful add/move/remove/care, area add/update/delete, undo, post; none for room create, follow, unsubscribe, photo, reads, 4xx - PASS (covered by `test_live.py`; add spot-checked live)
- [x] Tests per criterion, no endless `TestClient` stream - PASS

Tests: `uv run pytest app/test_live.py`, 5 passed, 0 failed; `uv run pytest`, 801 passed, 0 failed
