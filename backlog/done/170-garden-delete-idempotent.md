# [garden-delete] Make deleting a garden idempotent

## Goal

Two people confirming the delete at the same moment must not break anything: `DELETE /api/rooms/{roomId}` ([#150](done/150-garden-delete-api.md)) answers 204 when the garden is already gone, like the first call. Decision: this includes unknown and non-UUID ids (nothing to delete is also success). Reverses the 404 of #150 criterion 4 for DELETE only.

## Acceptance criteria

- [ ] A second delete, an unknown id and a non-UUID id give 204 with an empty body, no side effects and no error; one transaction as before. Of two deletes at the same moment both give 204, nothing is left, and only one calls `live.close_room`. Get, post, plant, area, follow and `/live` on the deleted room still give 404.
- [ ] `openapi.yaml` `deleteRoom` answers 204 only (no 404) and says it is idempotent.
- [ ] Frontend: `deleteRoom` returns true on 204 (a 404 from an old server still gives false); the mock never throws on a second delete. The UI flow is unchanged, no error toast.

## Constraints

- `backend/app/routers/rooms.py`, `backend/app/test_room_delete.py`, `openapi.yaml`, `frontend/src/services`. At most 2 tests changed or added.

## Comments

**Engineer:** `DELETE /api/rooms/{roomId}` (`routers/rooms.py`) now answers 204 always; the store transaction is unchanged (exclusive, one transaction), and `live.close_room` is called only by the delete that actually removed the room (`store.delete_room` returned True), so concurrent or repeated deletes cause no 404, 5xx or orphan rows. Unknown and non-UUID ids also give 204 (decision). Other calls on a deleted room still 404. `openapi.yaml` `deleteRoom`: 204 only, idempotent note. Frontend: the HTTP `deleteRoom` already gave true on 204 and false on 404 (kept for old servers); the mock now resolves true on a second delete (no throw, no second notify); the `GardenService.deleteRoom` doc comment says so. UI flow unchanged (the dialog treats true and false alike). Tests (2): `test_room_delete.py` 404 test replaced by an idempotent test (second, unknown, non-UUID give 204, other rooms untouched, `close_room` once, other calls 404) and a new two-thread test (both 204, nothing left, `close_room` once); mock test updated. `uv run pytest`: 128 passed, 2 skipped; `npm test` 40 passed; `npm run build` passes. Issue left open.
