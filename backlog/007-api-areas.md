# [api] Areas: add, update, delete

## Goal

`POST /api/rooms/{roomId}/areas`, `PATCH /api/areas/{areaId}` and `DELETE /api/areas/{areaId}` behave as `openapi.yaml` defines (`addArea`, `updateArea`, `deleteArea`), each writing one `area_changed` feed event with a `restore_area` undo payload.

## Acceptance criteria

- [ ] `POST` with a valid `AreaInput` returns 201 and a `RoomArea` (new UUID4 `id`, `room_id`, `deleted_at` null, trimmed `label`). It appears in `GET /api/rooms/{id}`; the room gains one feed event with text `added the area "Veg bed"`, the actor's name and device id, and undo payload `{kind: restore_area, area: null, area_id: <id>}`; the room's `last_activity_at` equals that event's `created_at`.
- [ ] `POST` gives 400, never 422, and writes nothing, for: a missing field, a blank `label` (`An area needs a label`), a label over 40 characters, an unknown `shape` or `colour`, any percent outside 0-100 (rejected, not clamped), or `w_pct`/`h_pct` of 0. An unknown or non-UUID room gives 404 `Room not found`.
- [ ] Adding to a room with 10 live areas gives 409 `This garden has the maximum 10 areas` and writes nothing; soft-deleted areas do not count, so a room with 10 areas, one of them deleted, accepts one more.
- [ ] `PATCH` changes only the fields sent, returns 200 with the full `RoomArea`, and writes one event whose undo payload holds the whole area as it was before. Text, first match wins: label changed `renamed "Veg bed" to "Herbs"`; `w_pct`/`h_pct` changed `resized the area "Herbs"`; `x_pct`/`y_pct` changed `moved the area "Herbs"`; only shape/colour `changed the area "Herbs"`.
- [ ] `PATCH` gives 400 with the area unchanged and no event for: an empty body, a body with no known fields, a `null` value, or any invalid value as in the `POST` rules. Sending values identical to the current ones gives 200 and writes no event and no activity bump. An unknown, non-UUID or soft-deleted area gives 404 `Area not found`.
- [ ] `DELETE` returns 204 with an empty body, the area leaves `GET /api/rooms/{id}`, and one event with text `removed the area "Herbs"` and undo payload holding the area as it was before is written. Deleting again, or an unknown or non-UUID id, gives 404 `Area not found`.
- [ ] All three require the actor headers (400 without, as in [#003](done/003-api-actor-auth.md)), and each success bumps `last_activity_at` and calls `notify(room_id)` once after the change is saved; no failure does either. `uv run pytest` passes, with tests per criterion using a fresh `Store` injected via `app.dependency_overrides[get_store]`.

## Out of scope

- Undoing area events: [#008](008-api-undo.md). The live stream behind `notify`: [#011](011-api-live-sse.md). Frontend wiring: [#014](014-api-frontend-wiring.md).

## Constraints

- Implement after [#006](006-api-room-plants.md), which creates `backend/app/live.py` with a no-op `notify(room_id)`; call it after committing, as 006 does. Code in `backend/app/routers/areas.py` (registered in `routers/__init__.py`), request models in `models.py`, tests in `backend/app/test_areas.py`. Wrap each mutation (limit check, area, event, room bump) in `store.transaction()`, use `Depends(get_actor)`, raise `ApiError`, take times from `app.timestamps.now()`. No new dependencies; follow `_docs/testing-guidelines.md`.

## Original request

**What:** `POST /rooms/{roomId}/areas`, `PATCH /areas/{id}` (partial) and `DELETE /areas/{id}` (soft delete). Each one writes an `area_changed` feed event with a `restore_area` undo payload, as defined in `openapi.yaml`. **Why:** These let people draw beds and ponds on the canvas.
**Edge cases:** Adding an 11th live area returns 409 `This garden has the maximum 10 areas`. A PATCH with an empty body returns 400 (`minProperties: 1`). Unlike plant moves, area percents outside 0–100 should be rejected with 400; the PM should confirm this. An unknown `colour` returns 400, even though the frontend tolerates it. A soft-deleted or unknown area returns 404 `Area not found`. The undo payload for an add has `area: null`. Rename text looks like `renamed "Veg bed" to "Herbs"`, and the PM should define the text for move, resize and delete.

## Comments
