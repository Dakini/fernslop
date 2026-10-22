# [api] Undo feed events
## Goal
`POST /api/feed-events/{eventId}/undo` behaves as `openapi.yaml` defines (`undoEvent`, `UndoPayload`), applying the payloads written by [#006](006-api-room-plants.md) and [#007](007-api-areas.md).
## Acceptance criteria
- [ ] Success returns 204 with an empty body. The event gets `undone_at` = now but keeps its `undo_payload`, stays in the room feed, and no new event is written. The room's `last_activity_at` equals `undone_at`, and `live.notify(room_id)` is called once, after the transaction ends.
- [ ] `restore_plant` writes the `room_plant` snapshot back as-is, clearing `deleted_at`: a removed plant reappears in `GET /api/rooms/{id}`, and a moved or cared-for plant returns to its old position/timestamps, even after newer edits.
- [ ] `delete_plant` soft-deletes the plant, and `restore_area` with `area: null` soft-deletes the area; both leave the room state. If the target is already soft-deleted, it stays deleted (original `deleted_at` kept) and the call still returns 204.
- [ ] `restore_area` with an area writes it back exactly (an area removed or edited is restored, and `deleted_at` is cleared).
- [ ] An event with no payload (a post) gives 409 `This can't be undone`; undoing twice gives 409 `Already undone`. Bringing back a soft-deleted plant into a room with 50 live plants gives 409 `This garden is full (50 plants max)`, and an area with 10 live areas gives `This garden has the maximum 10 areas`; undoing a move or care on a still-live plant is never blocked.
- [ ] An unknown or non-UUID event id gives 404 `Event not found`; missing or malformed actor headers give 400, never 422. Every 4xx/409 changes nothing (plants, areas, feed, `undone_at` null, `last_activity_at`) and does not call `live.notify`.
- [ ] `uv run pytest` passes, with tests per criterion using a fresh `Store` via `app.dependency_overrides[get_store]`, `live.notify` patched, and events created through the real 006/007 endpoints.
## Out of scope
- Making `notify` push to browsers: [#011](011-api-live-sse.md). Recording who undid an event, or redo: not in the spec. Frontend wiring: [#014](014-api-frontend-wiring.md).
## Constraints
- Implement after [#006](006-api-room-plants.md) (creates `backend/app/live.py`) and [#007](007-api-areas.md). Code in `backend/app/routers/feed_events.py` (registered in `routers/__init__.py`), tests in `backend/app/test_feed_events.py`. Use `Depends(get_store)` and `Depends(get_actor)`; do all checks and writes in one `store.transaction()`; reuse the 50/10 limit constants and messages from the 006/007 routers; times from `timestamps.now()`. No new dependencies; follow `_docs/testing-guidelines.md`.
## Original request
**What:** `POST /feed-events/{eventId}/undo` applies the event's `undo_payload` (`restore_plant`, `delete_plant` or `restore_area`) and sets `undone_at`. It writes no new feed event.
**Why:** The feed's undo button depends on it. It relies on the payloads written in 006 and 007.
**Edge cases:** An event with no payload (a post) returns 409 `This can't be undone`. Undoing twice returns 409 `Already undone`. Restoring a plant or area into a room that is at its limit returns 409 with the same messages as add. On any 409 nothing changes and `undone_at` stays null, so the operation must be atomic. An unknown event returns 404. Undoing an older event after newer edits writes the old snapshot back as-is, which is the spec's behaviour. Undo still requires the actor headers, and it bumps `last_activity_at` and the live stream.
## Comments

**Engineer:** Implemented `undoEvent` in `backend/app/routers/feed_events.py` (registered in `routers/__init__.py`), tests in `backend/app/test_feed_events.py` (32 tests, one or more per criterion). All checks (event exists, not already undone, has a payload, 50/10 limit) run before the first write inside one `store.transaction()`, so every 409 changes nothing. The limit applies only when the target is currently soft-deleted or missing and the snapshot is live (a move/care undo on a live plant is never blocked). Limit constants and messages are imported from the 006/007 routers (no refactor needed). `delete_plant` / `restore_area` with `area: null` on an already-deleted target keep the original `deleted_at` and still return 204 with `undone_at` set. Full suite: 737 passed. No criteria changed.

## QA: PASS

- [x] Success returns 204 empty; `undone_at` set, payload kept, event stays in feed, no new event, `last_activity_at` == `undone_at`, `live.notify` called once - PASS
- [x] `restore_plant` writes snapshot back as-is (remove, move, care undone; an older snapshot overwrote newer edits) - PASS
- [x] `delete_plant` / `restore_area` null soft-delete; already-deleted target stays deleted, 204 - PASS
- [x] `restore_area` with an area restores it (area delete and rename undone) - PASS
- [x] Post gives 409 `This can't be undone`; double undo 409 `Already undone`; full room (50 plants / 10 areas) gives the specified 409s with nothing changed, `undone_at` null, no notify; move undo on a live plant in a full room gives 204 - PASS
- [x] Unknown and non-UUID id gives 404 `Event not found`; missing/malformed actor headers give 400; no state change, no notify - PASS
- [x] Tests pass - PASS

Tests: `uv run pytest`, 737 passed, 0 failed. Also spot-checked each criterion once with a throwaway script via the real 006/007/009 endpoints.
