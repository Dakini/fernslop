# [audit] Make garden delete a soft delete with a retention window

## Goal

A wiped garden can be brought back for 7 days: `DELETE /api/rooms/{id}` marks the room deleted instead of removing it, a purge command removes it for good after 7 days, and an operator can restore it before then with a CLI script (`audit.md` 1, soft-delete bullet; `_docs/lovable-spec.md`: "Deletes are soft"). Decisions (user): delete stays open to anyone, with no owner check (no accounts, per the spec); retention is 7 days; restore is a CLI script, not an endpoint.

## Acceptance criteria

- [ ] `DELETE` sets `deleted_at` on the stored room and removes nothing. It keeps done [#170](done/170-garden-delete-idempotent.md): always 204, idempotent, and only the call that marks the room closes its `/live` streams.
- [ ] A soft-deleted room is missing from `GET /api/rooms` and answers 404 on every other room call (state, plants, areas, posts, follows, undo, `/live`) exactly like a missing room; `deleted_at` never appears in an API response; the digest skips it.
- [ ] `uv run python -m app.room_purge [--days 7]` hard-deletes rooms deleted more than 7 days ago with everything `delete_room` removes today (plants, areas, feed, follows, photos only that room used), leaves younger deletions and live rooms alone, prints how many it purged, and is safe to run twice.
- [ ] `uv run python -m app.room_restore --list` prints deleted rooms (id, name, deleted at); `uv run python -m app.room_restore <room id>` clears `deleted_at` and the room is back with its plants, areas, feed and follows; an unknown, live or purged id exits non-zero with a clear message and changes nothing.
- [ ] Seed gardens are never re-created or duplicated by deleting, purging or restoring one (seeding stays keyed on `meta.seeded` in `sql_store.py`); a restored seed garden appears once.
- [ ] `openapi.yaml` (`deleteRoom` and the "Soft deletes" section) describes the soft delete and the 7-day purge. The delete dialog copy stays as is: users cannot undo, only an operator can.
- [ ] Tests: a deleted room is not listed and gives 404; purge respects the 7 days; restore brings everything back.

## Out of scope

- Running the purge on the deployed stack: [#198](198-audit-photo-storage.md).
- Photos of a soft-deleted room stay reachable by their URL until the purge: accepted.

## Constraints

- `backend/app/models.py`, `sql_store.py`, `store.py`, `routers/rooms.py` (other routers only if their 404 does not already go through `get_room`), `digest.py`, new `app/room_purge.py` and `app/room_restore.py`, `openapi.yaml`.
- `deleted_at` is a pydantic field with default `None` in the room's JSON `json` column, not a SQL column (migrations are parked, [#140](parked/140-db-migrations.md)); rows without it load as live. Filter deleted rooms in one place in the store, with separate methods for purge and restore.
- At most 5 tests.

## Comments

**Engineer:** Implemented in `f041fa6`. `StoredRoom(Room)` in `models.py` adds `deleted_at: Timestamp | None = None`, kept in the room JSON (no SQL column; old rows load as live). `SqlStore` reads rooms through `_stored_rooms`, and `_live_rooms` is the one place deleted rooms are dropped: `get_room`/`list_rooms` hand routers plain `Room`s of live rooms only, so `deleted_at` never reaches a response, every room call (state, plants, areas, posts, follows, undo, `/live`, and the child routes `/room-plants/{id}`, `/feed-events/{id}/undo`) 404s through its existing `get_room` check, and the digest skips deleted rooms. No other router needed a change. `delete_room(room_id, deleted_at)` marks a live room and returns whether this call marked it, so the router keeps the 204/idempotent/close-streams-once behaviour from #170. The off-protocol methods `list_deleted_rooms`, `restore_room` and `purge_deleted_rooms` (hard delete as before, including photos only that room used, all in one transaction) back the new `app/room_purge.py` (`--days`, default 7, prints `Purged N room(s)`) and `app/room_restore.py` (`--list`, or `<room id>`; unknown, live or purged ids exit 1 with a message on stderr). Seeding is still keyed on `meta.seeded`, so nothing is re-seeded. `openapi.yaml`: the `deleteRoom` summary/description and the "Soft deletes" section now describe the soft delete, the 7-day purge and the operator restore (`openapi-spec-validator`: OK). Frontend dialog copy is unchanged. Tests in `backend/app/test_room_delete.py`: rewrote the old hard-delete tests (delete hides the room but keeps its data across a restart; the 404 test also covers child routes; the concurrent test checks the room is marked once), dropped the "fails midway" test because a soft delete is a single write, moved the photo test into a new purge test (8-day deletion purged with plants/areas/feed/follows/own photo, 6-day one kept, shared photo kept, second run purges 0), and added a restore test (list, restore brings back state and follows, appears once; re-restore, live and unknown ids exit 1). `uv run pytest`: 136 passed, 2 skipped. `uvx ruff check .`: clean.
