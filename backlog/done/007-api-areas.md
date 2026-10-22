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

- Engineer: implemented `addArea`, `updateArea` and `deleteArea` in `backend/app/routers/areas.py` (registered in `routers/__init__.py`), with `AreaInput`/`AreaPatch` request models in `models.py` (strict types, trimmed label, percents rejected outside 0-100, `w_pct`/`h_pct` > 0) and tests in `backend/app/test_areas.py`. All criteria implemented unchanged; `uv run pytest` passes (643 tests). Interpretation notes: a label over 40 characters is measured after trimming (message `An area label can be at most 40 characters`); a PATCH value is "identical" when it equals the stored value after trimming the label, so a PATCH of only identical values returns 200 with no event, activity bump or `notify`; fields in a PATCH that equal the current value are ignored when choosing the event text; the body is validated before the room/area lookup, so an invalid body for an unknown id gives 400, as in 006.

## QA: PASS

- [x] POST valid AreaInput: 201, RoomArea (UUID4 id, room_id, deleted_at null, trimmed label), in GET room, one event `added the area "Veg bed"` with actor name and device id, undo `{kind: restore_area, area: null, area_id}`, `last_activity_at` equals the event's `created_at` - PASS
- [x] POST 400 (never 422), nothing written, for missing field, blank label (`An area needs a label`), label over 40, unknown shape/colour, percents outside 0-100 (not clamped), w/h of 0, string/null numbers, non-JSON, non-object body; unknown or non-UUID room 404 `Room not found` - PASS
- [x] 11th live area 409 `This garden has the maximum 10 areas`, nothing written; with 10 areas and one soft-deleted, one more is accepted, then 409 again - PASS
- [x] PATCH changes only the sent fields, returns 200 with the full RoomArea, one event whose undo payload is the whole area before the change; text rename / resized / moved / changed, first match wins (checked combined bodies such as label+resize, resize+move, move+colour) - PASS
- [x] PATCH 400 with area unchanged and no event/notify for empty body, unknown-only fields, null values, and each invalid value from the POST rules; identical values (also with a padded label or an int-vs-float percent) give 200 with no event, no activity bump, no notify; unknown, non-UUID or soft-deleted area 404 `Area not found` - PASS
- [x] DELETE 204 with empty body, area gone from GET room, one event `removed the area "<label>"` with the pre-delete area as undo payload; second delete and unknown or non-UUID id give 404 `Area not found` - PASS
- [x] All three require actor headers (400 for none, missing or blank device id, missing or blank name; nothing written or notified); each success bumps `last_activity_at` and calls `live.notify(room_id)` once; no failure (400/404/409) does - PASS

Tests: `uv run pytest`, 682 passed, 1 failed (`app/test_identify.py::test_plantnet_httpx_request_log_line_has_the_key_redacted`, issue 012's in-progress work, unrelated to areas); `uv run pytest app/test_areas.py`, 91 passed, 0 failed. Also ran my own throwaway script exercising every case above against a fresh injected `Store` (103 checks, all matching the criteria).

Note (not a criterion): `Store.transaction()` does not roll back, so if saving the feed event raised after `save_area`, the area change would persist without an event. This is the store's documented behaviour from issue 002, not a 007 defect.
