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

### Engineer (implementation)

Implemented `GET/POST /api/rooms` and `GET /api/rooms/{roomId}` in `backend/app/routers/rooms.py` (registered in `routers/__init__.py`), with `RoomSummary`, `RoomSummaryPlant` and `RoomState` added to `models.py`. 51 tests in `backend/app/test_rooms.py` cover each criterion using a fresh `Store` via `app.dependency_overrides[get_store]`; `uv run pytest` passes (338 passed). Interpretation notes: the body is parsed by hand so bad JSON or a non-object is a 400, not 422; a non-string `description`/`region` gives 400 `Description must be a string` / `Region must be a string` (the issue does not specify this); a room plant whose plant is missing from the reference table is skipped in both the summary and the room state.

### QA

## QA: PASS

- [x] `GET /api/rooms` on the seed returns three summaries, newest `last_activity_at` first, live plants/areas only, missing-plant rows skipped - PASS
      Seed returned Elm Street, Balcony, Orchard in descending order. Elm Street has 5 room plants (4 live) and the summary shows 4. Balcony has 2 areas (1 live) and the summary shows 1. A room plant with an unknown `plant_id` was skipped in both the list and the state, with no 500. Tie ordering by `created_at` is covered by `test_list_rooms_orders_by_last_activity_then_newest_created`.
- [x] `POST /api/rooms` trims fields, returns 201, `region` `""`, UUID4 id, `created_at == last_activity_at`, ignores extra fields - PASS
      Posted `{"name": "  Back Yard  ", "description": " Sunny ", "id": "x", "created_at": "2000-...", "foo": 1}` and got `Back Yard` / `Sunny` / `""`. The client-sent `id` and `created_at` were ignored.
- [x] New room is first in the list, has empty `plants`/`areas`/`feed`, and duplicate names succeed with different ids - PASS
- [x] Missing, non-string, empty or whitespace-only `name` gives 400 `A room needs a name` - PASS
      Tried `{}`, null, 5, true, `[]`, `{}`, "" and "   \t\n ". All gave the exact message.
- [x] Length limits (60/200/60 after trimming) and invalid JSON handling - PASS
      60/200/60 accepted, including padded input. 61/201/61 gave `Name must be at most 60 characters`, `Description must be at most 200 characters` and `Region must be at most 60 characters`. Bad JSON, an empty body, no body, `[]`, `"s"`, `null`, `5`, form-encoded and non-UTF-8 bodies all gave 400, never 422.
- [x] `GET /api/rooms/{id}` returns the full feed newest first including undone events; unknown ids give 404 `Room not found` - PASS
      Elm Street's feed has 11 events, one with `undone_at` set, in descending `created_at`. State plants and areas hold no soft-deleted rows. `nope`, `123`, a never-created UUID, the nil UUID, a 500-character id and `%20` all gave 404 `{"message": "Room not found"}`.
- [x] Actor headers missing or malformed still give 201 and no feed event; tests exist per criterion with a fresh injected `Store` - PASS
      Tried no headers, an empty device id, a bad percent-encoded name and a control character. The new room's feed was empty.

Tests: `uv run pytest`, 338 passed, 0 failed (`uv run pytest app/test_rooms.py`, 51 passed). I also ran an independent script against a fresh `Store` via `dependency_overrides`, covering the cases above.
