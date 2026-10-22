# [garden-delete] API: delete a garden (room) for good

## Goal

`DELETE /api/rooms/{roomId}` (`deleteRoom`) hard-deletes a garden and everything in it. Anyone with the link can call it, no actor headers (default decision; accounts do not exist and the confirm dialog in [#160](160-garden-delete-ui.md) is the only guard). Hard, not soft: the feed that undo lives in goes with the room, and follower emails and photos of a "deleted" garden would be a privacy leak.

## Acceptance criteria

- [ ] Deleting an existing room (created or seeded) with no headers returns 204 and an empty body; then `getRoomState` gives 404 and `listRooms` no longer lists it. A seeded room stays gone after the app restarts.
- [ ] Its plants and areas (including soft-deleted ones), feed events (including undone ones) and follows are gone from the database, not just hidden; a follow's old unsubscribe link still answers "already unsubscribed"; `build_digests` no longer sees the room and sends nothing for it. The shared `plants` reference table is unchanged.
- [ ] A photo that only this room's feed events point at is gone (`GET /photos/{id}` is 404); a photo another room's post also points at stays, as does an unposted upload (left to `app.photo_cleanup`).
- [ ] A second delete, an unknown id and a non-UUID id all give 404 with message `Room not found` (never 422); afterwards post, plant, area, follow and `/live` calls for that room give 404 as for any missing room.
- [ ] It is one store transaction: if any step fails the room and all its data are unchanged. A post, plant add or follow running at the same moment either finishes before the delete or gets 404, and leaves no orphan rows.
- [ ] Open `/rooms/{id}/live` streams get a `change` message and then end, so `live.subscriber_count(room_id)` is 0 afterwards; this happens only after the delete commits.
- [ ] `openapi.yaml` has the `deleteRoom` entry (204, 404 with `Error`, no `security`) and its "Soft deletes" section says rooms are the exception and are hard-deleted.

## Out of scope

- The delete button and dialog: [#160](160-garden-delete-ui.md). Live streams across several workers: [#090](parked/090-api-live-multi-worker.md).

## Constraints

- Only `SqlStore` exists now (the in-memory `Store` is gone; tests use `SqlStore("sqlite://")`): add one `StoreProtocol` method in `app/store.py`, implement it in `app/sql_store.py` for SQLite and Postgres, router in `app/routers/rooms.py`. `live.py` has no way to end streams yet: add one and call it as `live.<fn>(room_id)` after the commit, like `notify`.
- `follows.py` checks the room before its transaction: re-check inside it. Photos are matched by `feed_events.photo_url` = `photos.url`.
- No new dependencies (AGENTS.md). Read `_docs/testing-guidelines.md` first; at most 5 new tests, e.g. happy path with all data, photo rules, the 404 cases, rollback, live release.

## Comments

**Engineer:** Added `DELETE /api/rooms/{roomId}` (`deleteRoom`, 204, no actor headers) in `backend/app/routers/rooms.py`. New `StoreProtocol.delete_room(room_id) -> bool` in `store.py`, implemented in `sql_store.py`: one transaction that deletes the room row (False if it did not exist), then its plants and areas (including soft-deleted), feed events (including undone) and follows, then any photo whose url only this room's events used (a photo another room's event also uses, or one no event uses, stays; the `plants` reference table is untouched). The seeded flag lives in `meta`, so a deleted seeded room is not re-seeded on restart. The router calls the new `live.close_room(room_id)` only after the transaction commits; it drops the room's subscribers from the count at once and gives each stream one last `change` and then ends it (`live.py`; `event_stream` returns after a closed `change`). `follows.py` now re-checks the room inside its transaction; posts, plant add and area add already did. `openapi.yaml` has the `deleteRoom` entry (204, 404 with `Error`, no `security`) and the "Soft deletes" section says rooms are hard-deleted. 5 new tests in `backend/app/test_room_delete.py` (all data plus restart, photo rules, the 404 cases and calls afterwards, failure midway changes nothing and does not close streams, live streams end with subscriber count 0). Not tested directly: the concurrent post/follow race (it relies on the in-transaction room checks and the store lock) and the frontend client (`frontend/src/services`), which is for #160. Results: `uv run pytest` on SQLite 127 passed, 2 skipped (Postgres-only); with `FERNSLOP_TEST_DATABASE_URL` against `postgres:17-alpine` in docker, 129 passed. Issue left open.
