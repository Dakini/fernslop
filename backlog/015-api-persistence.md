# [api] Follow-up: persistent storage and photo cleanup

## Goal

Data and photos survive a restart when `FERNSLOP_DB_PATH` is set: a SQLite store (stdlib `sqlite3`, no ORM, no external service) implements `StoreProtocol`, and a command removes photos nobody posted.

## Acceptance criteria

- [ ] `get_store()` returns the SQLite store (file created on first use) when `FERNSLOP_DB_PATH` is set and the in-memory `Store` when unset; with it unset `uv run pytest` passes unchanged, and with it set to a temp file the whole suite passes too.
- [ ] A new store opened on the same file sees earlier writes (a room, a plant, an event with `undo_payload`, a follow, a photo with byte-identical `data`); `GET /photos/{id}` returns the same bytes after the store object is rebuilt.
- [ ] A missing or empty database gets the demo seed once; reopening a file never re-seeds, so a seeded room edited or a follow deleted stays that way. `reset()` still restores the seed (the test fixture uses it).
- [ ] `transaction()` is atomic on both stores: if the block raises, every save and delete in it is undone and the exception still propagates; nested use works and the outermost exit decides. Replaces the old "does not roll back" test, and 007's QA note (no event, area changed) no longer holds.
- [ ] Safe under threads: 20 threads each doing read-count-then-save in a `transaction()` end with exactly 20 records and no "database is locked" error; a reader outside a transaction never sees half of one.
- [ ] The existing `test_store.py` behaviour tests (copies, replace keeps position, feed order incl. ties, case-insensitive email, soft-deleted filters, seed, reset, threads) run against both stores via one parametrised fixture, with identical results.
- [ ] `uv run python -m app.photo_cleanup [--hours N]` (default 24) deletes photos older than N hours that no feed event's `photo_url` references, in one transaction, and prints how many; younger, referenced and seeded photos stay; `GET /photos/{id}` of a deleted one is 404. Without `FERNSLOP_DB_PATH` it exits non-zero with a message and deletes nothing. Has tests.

## Out of scope

- Live updates across several workers: [#090](090-api-live-multi-worker.md). Serving and deploying the app: [#120](120-api-deploy-together.md). Scheduling the cleanup (cron) and moving to a server database or object storage: not planned.

## Constraints

- Code in new `backend/app/sqlite_store.py` and `photo_cleanup.py`; selection stays in `get_store()` in `store.py`; `StoreProtocol` gains no required method, routers stay untouched. Photos go in a BLOB column. No new dependencies; follow `_docs/testing-guidelines.md`.

## Original request

**What:** Replace the in-memory store with a real database and file/object storage, and clean up photos that were never posted. **Why:** Moved out of 002 and 009; the request asked for in-memory storage, so all data is lost on restart. **Edge cases:** The undo and limit checks must stay atomic under concurrent requests.

## Comments
