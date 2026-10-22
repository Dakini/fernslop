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

**Engineer:** Added `backend/app/sqlite_store.py` (stdlib `sqlite3`, WAL, `BEGIN IMMEDIATE` plus an RLock; records as JSON next to a few indexed columns, photos in a BLOB) and `backend/app/photo_cleanup.py`. `get_store()` in `store.py` returns the SQLite store (cached per path) when `FERNSLOP_DB_PATH` is set, otherwise the in-memory `Store`. Seeding happens once, flagged in a `meta` table; `reset()` restores the seed. `transaction()` now rolls back on both stores (in-memory by snapshotting its dicts; nested use is decided by the outermost block). The existing `test_store.py` behaviour tests run against both stores via one `new_store` fixture; 5 new tests (rollback, 20 threads plus no half-transaction reads, restart persistence and no re-seed, two cleanup tests). `conftest.py` resets both the in-memory store and `get_store()`. The suite passes with and without `FERNSLOP_DB_PATH`. Note: `digest.main()` still uses the in-memory `store` (its tests patch `app.store.store`); pointing it at `get_store()` is a one-line follow-up for whoever picks that up.

**QA:**

## QA: PASS

- [x] `get_store()` picks SQLite when `FERNSLOP_DB_PATH` is set, in-memory when unset; suite passes both ways - PASS
- [x] A new store on the same file sees earlier writes (room edit, event, photo with byte-identical data); `GET /photos/{id}` after rebuild covered by suite - PASS
- [x] Seed once, no re-seed on reopen (edited seeded room stayed edited after reopen); `reset()` covered by suite fixture - PASS (no seeded follows exist, so follow deletion was not exercised by hand)
- [x] `transaction()` atomic on both stores: raised error undid two saves and still propagated; nested outer exit decides - PASS
- [x] 20 threads read-count-save test and half-transaction reader test exist and pass on both stores - PASS
- [x] `test_store.py` runs against both stores via one parametrised `new_store` fixture - PASS
- [x] `python -m app.photo_cleanup`: deleted only the old unreferenced photo (old posted, young orphan and seeded photo stayed), printed "Deleted 1 photo(s)"; without `FERNSLOP_DB_PATH` it printed a message and exited 1 - PASS

Tests: `uv run pytest`, 801 passed, 0 failed (also with `FERNSLOP_DB_PATH` set to a temp file: 801 passed). No hang in either run (~9s each; ran with a 120s watchdog since macOS has no `timeout`).
