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
