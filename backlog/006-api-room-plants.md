# [api] Room plants: add, move, remove, mark care

## Goal

`POST /api/rooms/{roomId}/plants`, `PATCH`/`DELETE /api/room-plants/{id}` and `POST /api/room-plants/{id}/care` behave as `openapi.yaml` defines (`addPlant`, `movePlant`, `removePlant`, `markCare`), on the store from [#002](002-api-seed-store.md), each writing the feed event that [#008](008-api-undo.md) later undoes.

## Acceptance criteria

- [ ] Add with `{"plant_id": "<seeded id>"}` returns 201 and a `RoomPlant` at 50/50, `nickname` and all `last_*_at` null, `added_by_name` the actor's name, a new UUID4 `id`; it shows in `GET /api/rooms/{id}`. Unknown room gives 404 `Room not found`, unknown `plant_id` 404 `Plant not found`, a missing or non-string `plant_id` 400 (never 422).
- [ ] A room with 50 live plants answers add with 409 `This garden is full (50 plants max)`; with 49 live plus any number soft-deleted, add succeeds.
- [ ] Move returns 200 with the updated `RoomPlant`; coordinates are clamped to 0-100 (`-5` gives 0, `250` gives 100) and floats are kept. A missing, non-number, boolean or null coordinate gives 400.
- [ ] Remove returns 204 with an empty body, sets `deleted_at`, and the plant leaves the room state. A repeat remove, an unknown id, and move or care on a removed plant all give 404 `Plant is no longer in this garden`.
- [ ] Care `{"care": "water"}` sets only the matching timestamp (water, feed, prune, harvest map to `last_watered_at`, `last_fed_at`, `last_pruned_at`, `last_harvested_at`) to now and returns 200. A plant whose interval is null or 0 gives 422 `No water data for this plant` (care name inserted); a missing or unknown `care` gives 400.
- [ ] Each success writes exactly one feed event (type, `room_plant_id`, actor name and device id from the headers, `undone_at` null), shown first in the room state, with the undo payload from `openapi.yaml`: `delete_plant` for add; for move, remove and care `restore_plant` holding the `RoomPlant` exactly as it was before. `text` is `added a`, `moved the`, `removed the` or `watered`/`fed`/`pruned`/`harvested the`, then the nickname or else `common_name`. The room's `last_activity_at` equals the event's `created_at`, from one `timestamps.now()` per request.
- [ ] All four reject missing or malformed actor headers with 400. Every 4xx leaves plants, feed and `last_activity_at` untouched and does not call `live.notify`; every success calls `live.notify(room_id)` exactly once, after its transaction ends. `uv run pytest` passes with tests per criterion, using a fresh `Store` via `app.dependency_overrides[get_store]`.

## Out of scope

- Applying undo payloads and their 409/404 cases: [#008](008-api-undo.md). Making `notify` push to browsers: [#011](011-api-live-sse.md). Frontend wiring: [#014](014-api-frontend-wiring.md).

## Constraints

- Routes in `backend/app/routers/room_plants.py` (registered in `routers/__init__.py`), tests in `backend/app/test_room_plants.py`. Use `Depends(get_store)` and `Depends(get_actor)`; check, save plant, save feed event and bump the room inside one `store.transaction()`; raise `ApiError`. Create `backend/app/live.py` with a no-op `notify(room_id: str) -> None`; routers call it as `live.notify(...)` so tests can patch it, and 007-009 reuse it. No new dependencies; follow `_docs/testing-guidelines.md`.

## Original request

**What:** `POST /rooms/{roomId}/plants`, `PATCH`/`DELETE /room-plants/{id}`, `POST /room-plants/{id}/care`, each writing a feed event (`plant_added`, `plant_moved`, `plant_removed`, `care_done`) with the undo payload in `openapi.yaml`. **Why:** Main garden canvas interactions; undo (008) works from the events.
**Edge cases:** New plant at 50/50. A 51st live plant gives 409 `This garden is full (50 plants max)`; soft-deleted don't count. Unknown `plant_id` 404. Move clamps to 0-100. Soft-deleted or unknown room plant 404 `Plant is no longer in this garden`. Care 422 `No <care> data for this plant` when the interval is null or 0. `restore_plant` is a snapshot from before the change. Every mutation bumps `last_activity_at`. Feed `text` is a fragment such as `added a Tomato`.

## Comments
