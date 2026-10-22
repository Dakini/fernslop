# [audit] Undo must not revert later changes

## Goal

Undo never silently overwrites a later change: undoing an event is refused with 409 while a later, not-undone event exists for the same plant or area, and the UI shows why (`audit.md` 6). Decision: the 409 check rather than storing diffs, because it works unchanged for the full snapshots existing feed events already hold.

## Acceptance criteria

- [ ] Move a plant, water it, undo the move: 409 `Undo the later changes to this plant first`, and nothing changes (position and `last_watered_at` stay, the move stays not undone). Undoing the watering first and then the move works.
- [ ] The rule covers every undoable plant event (added, moved, care, removed), matched on `room_plant_id`, and every area event, matched on the area id in `RestoreAreaPayload`: rename an area, move it, undo the rename gives 409 `Undo the later changes to this area first`.
- [ ] "Later" means after the event in feed order (`created_at`, then save order); undone events and posts never block, nor do events of other plants or areas.
- [ ] Existing feed events follow the same rule with no data change. An already undone event still gives 409 `Already undone` (checked first), and the plant and area limit checks still apply after this one.
- [ ] Of two undos sent at once for the same plant, at most one succeeds when the other would revert it (the check and the write share the one store transaction, as today).
- [ ] The UI shows the 409 message as a toast, like other undo errors, and the plant or area stays put. `openapi.yaml` `undoEvent` lists both messages under 409 and the mock service behaves the same.

## Out of scope

- Nothing moved out of this issue.

## Constraints

- `backend/app/routers/feed_events.py` (a store helper only if needed), `openapi.yaml`, `frontend/src/services/mock/mockService.ts`; the room page only if the toast is missing.
- No change to the undo payload format. At most 4 tests.

## Comments

**Engineer:** Implemented in `backend/app/routers/feed_events.py`: after the `Already undone` and `This can't be undone` checks and before the plant/area limit checks, `_check_no_later_changes` walks the room's feed (newest first: `created_at`, then save order) and returns 409 `Undo the later changes to this plant first` / `... this area first` if a later, not-undone event targets the same plant (`room_plant` id / `room_plant_id` from the undo payload) or area (`area_id`). Posts, undone events and other plants/areas never block. It runs inside the existing store transaction, so check and write stay atomic; no payload or data change, no store helper needed. `openapi.yaml` `undoEvent` 409 lists both messages and the rule; the mock service applies the same rule (save order). The room page already toasts undo errors via `run()`, so no UI change. Tests: 3 backend (move+water+undo move 409 then undo in order works; area rename+move gives 409; other plant/post don't block) and 1 mock test. Backend `uv run pytest`: 137 passed, 2 skipped; `uvx ruff check .` clean; frontend `npm test`: 41 passed.
