# [api] Rooms: list, create, get state

## Goal

`GET /api/rooms`, `POST /api/rooms` and `GET /api/rooms/{roomId}` behave as `openapi.yaml` defines (`listRooms`, `createRoom`, `getRoomState`), served from the store in [#002](002-api-seed-store.md).

## Acceptance criteria

- [ ] `GET /api/rooms` on the seed returns the three seeded `RoomSummary` objects, newest `last_activity_at` first (ties: newest `created_at`). Summaries and room state hold only live plants and areas; a room plant whose plant is missing from the reference table is skipped, not a 500.
- [ ] `POST /api/rooms` with `{"name": "  Back Yard  ", "description": " Sunny "}` returns 201 and a `Room` with trimmed fields, `region` `""`, a new UUID4 `id` and `created_at == last_activity_at`. Extra body fields are ignored.
- [ ] The new room is first in `GET /api/rooms` and its `GET /api/rooms/{id}` has empty `plants`, `areas` and `feed`. Two rooms with the same name both succeed with different ids.
- [ ] A missing, non-string, empty or whitespace-only `name` gives 400 `A room needs a name`.
- [ ] After trimming, name/region of 60 and description of 200 characters are accepted and one more gives 400 `<Name|Description|Region> must be at most <n> characters`; nothing is truncated. Invalid JSON or a non-object body also gives 400, never 422.
- [ ] `GET /api/rooms/{roomId}` on a seeded room returns `room`, live `plants` and `areas`, and the full `feed` newest first including events with `undone_at` set. An unknown id, `nope` and a never-created UUID all give 404 `Room not found`, never 422.
- [ ] `POST /api/rooms` works with actor headers missing or malformed and writes no feed event. `uv run pytest` passes, with tests per criterion using a fresh `Store` injected via `app.dependency_overrides[get_store]`.

## Out of scope

- Mutations that bump `last_activity_at`: [#006](006-api-room-plants.md), [#007](007-api-areas.md). Room creation sends no `change` message, so no `notify(room_id)` hook is added here; [#011](011-api-live-sse.md) defines it for those issues. Frontend wiring: [#014](014-api-frontend-wiring.md).

## Constraints

- Code in `backend/app/routers/rooms.py` (registered in `routers/__init__.py`), new models beside `Room` in `models.py`, tests in `backend/app/test_rooms.py`. Use only `StoreProtocol` methods via `Depends(get_store)`, raise `ApiError`, take times from `app.timestamps.now()`. No new dependencies; follow `_docs/testing-guidelines.md`.

## Original request

**What:** `GET /rooms`, `POST /rooms` and `GET /rooms/{roomId}`, as defined in `openapi.yaml`. **Why:** These power the index page and the room page.
**Edge cases:** Trim all fields. A name that is empty or only whitespace returns 400 `A room needs a name`. Enforce max lengths of 60/200/60. Two rooms with the same name are allowed. `last_activity_at` starts at `created_at`. The list is sorted by `last_activity_at`, newest first, and its summaries contain only live plants and areas. The state includes the full feed, newest first, including undone events. An unknown or non-UUID `roomId` returns 404 with an `Error` body, not FastAPI's 422.

## Comments
