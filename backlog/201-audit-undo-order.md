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

## QA: PASS

- [x] Move, water, undo the move gives 409 `Undo the later changes to this plant first` and nothing changes; undoing the watering then the move works - PASS
      TestClient: 409 with that message, room plant unchanged (position and `last_watered_at`), move `undone_at` still null; then undo watering 204, undo move 204, plant back to its original state
- [x] Covers added, moved, care, removed (by `room_plant_id`) and area events (by `area_id`) - PASS
      Undo of an add after a later move: 409 plant message; undo of a move after a later removal: 409 plant message; area rename then move, undo rename: 409 `Undo the later changes to this area first`, label stays
- [x] "Later" is feed order; undone events, posts, other plants and other areas never block - PASS
      Moved plant A, moved plant B, renamed an area, posted, moved A again: undo of A's later move 204, then A's earlier move 204 (the undone later move no longer blocks)
- [x] Existing feed events follow the rule with no data change; `Already undone` checked first; limit checks still apply after - PASS
      On the unmodified seed, undoing oldest first: seeded "added Tomato" and "added Lettuce" give 409 (later watering / removal stand), others 204. `Already undone` is checked before the new rule in the router; existing tests for already undone and garden/area limits pass
- [x] Two simultaneous undos for the same plant: at most one succeeds when the other would revert it - PASS
      Two threads undoing an earlier and a later move of the same plant at once: later 204, earlier 409, plant at the earlier position; the check runs inside the store transaction. Same event twice at once: one 204, one `Already undone`
- [x] UI shows the 409 as a toast and the item stays put; `openapi.yaml` lists both messages; mock behaves the same - PASS
      Room page undo goes through `run()`, which toasts the error message from the http service and changes nothing; `undoEvent` 409 in `openapi.yaml` names both messages; mock `undoEvent` applies the same rule with both messages (mock test covers the plant case)

Tests: `cd backend && uv run pytest`, 137 passed, 2 skipped, 0 failed; `cd frontend && npm test`, 41 passed, 0 failed
