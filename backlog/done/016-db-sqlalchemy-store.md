# [db] Replace the in-memory store with a SQLAlchemy database store

## Goal

One `StoreProtocol` implementation on SQLAlchemy replaces the in-memory `Store` and the raw-`sqlite3` `SqliteStore`. Data survives restarts by default, and the database is chosen by a SQLAlchemy URL so Postgres can be added later ([#130](../parked/130-db-postgres.md)).

## Acceptance criteria

- [ ] `get_store()` builds the store from env `FERNSLOP_DATABASE_URL`; unset, it uses `sqlite:///fernslop.db` (relative to the working dir, ignored by git, created on first use). `FERNSLOP_DB_PATH` is no longer read anywhere. Routers are unchanged.
- [ ] The in-memory `Store` and `sqlite_store.py` are deleted; `uv run pytest` passes using SQLite URLs (in-memory or `tmp_path`) only, and afterwards no `fernslop.db` exists in the repo.
- [ ] The behaviour tests in `test_store.py` (copies, replace keeps position, feed order incl. ties, case-insensitive email, soft-deleted filters, threads) still pass against the new store.
- [ ] Restart: a new store on the same URL sees earlier writes, incl. a photo with byte-identical `data`; the demo seed is applied once to an empty DB and never again on reopen; `reset()` restores it.
- [ ] `transaction()` rolls back every save/delete if the block raises (exception still propagates), nests with the outermost exit deciding, and is exclusive across threads in one process: 20 threads doing read-count-save end with exactly 20 records, no "database is locked", and no reader sees half a transaction.
- [ ] Portable: the schema is created with `create_all` using only portable SQLAlchemy types (records may stay JSON text next to a few indexed columns); SQLite-specific code (pragma, `BEGIN IMMEDIATE`) lives only in connection setup and runs only when the dialect is sqlite.
- [ ] `python -m app.photo_cleanup [--hours N]` and `digest.main()` use the configured DB (no env var required any more); cleanup keeps its behaviour from [#015](015-api-persistence.md) (older, unreferenced photos only; one transaction; prints the count).

## Out of scope

- Postgres driver, running the suite on it and cross-process `transaction()` locking: [#130](../parked/130-db-postgres.md). Alembic migrations: [#140](../parked/140-db-migrations.md).
- Importing data from an existing `FERNSLOP_DB_PATH` file: not planned.

## Constraints

- Stay in `backend/`: `store.py`, a new SQLAlchemy store module, `photo_cleanup.py`, `digest.py`, `conftest.py`, `.gitignore`. `StoreProtocol` gains no required method.
- Add `sqlalchemy` with `uv add` (user-approved); no other new dependency. At most 5 new tests (adapting or moving existing ones is free); follow `_docs/testing-guidelines.md`.

## Original request

**What:** Replace `Store` (in-memory) and the raw-`sqlite3` `SqliteStore` ([#015](015-api-persistence.md)) with one `StoreProtocol` implementation on SQLAlchemy, SQLite by default. The database is chosen by one environment variable holding a SQLAlchemy URL (replaces `FERNSLOP_DB_PATH`), and nothing outside the connection setup may be SQLite-specific, so Postgres can be added later ([#130](../parked/130-db-postgres.md)). Routers stay untouched. **Why:** The user asked for a real database via SQLAlchemy that is database-agnostic; today the default store loses all data on restart and the persistent one is stdlib-only and SQLite-bound. Adding the `sqlalchemy` dependency is explicitly approved by the user. **Edge cases:** `transaction()` must stay atomic, re-entrant and exclusive under threads (undo and 50-plant limit checks, see #015); photos (bytes), `undo_payload`, insertion order, feed-order ties and case-insensitive follow emails must behave as before; seed once on an empty DB, `reset()` restores it; `photo_cleanup` and `digest.main()` must use the configured DB; tests must not touch a developer's real DB file; schema is created with `create_all` (migrations are [#140](../parked/140-db-migrations.md)).

## Comments

**Engineer:** Added `backend/app/sql_store.py`: `SqlStore(url, *, seed=True)` on SQLAlchemy 2 Core with portable types (`create_all`, records as JSON text next to a few indexed columns, `seq` for insertion order, photos in a `LargeBinary` column, a `meta` table for the seeded flag) and a select-then-insert-or-update save, so a replaced record keeps its position. `transaction()` is an RLock plus one database transaction on a held connection (re-entrant, outermost block decides, rollback on any exception); methods outside a transaction use their own short one. All SQLite-specific code (WAL and synchronous pragmas, `check_same_thread`, busy timeout, `BEGIN IMMEDIATE` via the pysqlite connect/begin events, StaticPool for in-memory URLs) is in `_make_engine` and only applied for the sqlite dialect. `get_store()` reads `FERNSLOP_DATABASE_URL` (default `sqlite:///fernslop.db`) and caches one store per URL; `close_stores()` drops the cache. `Store` and `sqlite_store.py` are deleted, `FERNSLOP_DB_PATH` is gone, `photo_cleanup` and `digest.main()` use `get_store()` (cleanup no longer needs an env var). `conftest.py` sets `FERNSLOP_DATABASE_URL=sqlite://` per test and resets the cache; `fernslop.db*` is in `.gitignore`; `sqlalchemy` added with `uv add`; testing guidelines and the Makefile mention the new setup.

Tests: other test modules build `SqlStore("sqlite://")`; the restart test now uses a `tmp_path` URL and the cleanup test a `tmp_path` URL. 4 new tests in `test_sql_store.py` (default URL creates `fernslop.db` in the working dir, replace-keeps-position with feed ties, case-insensitive follow email, 20 threads read-count-save on a file DB with no errors); the restart test moved there from `test_store.py`. Note for QA: HEAD's suite was already pruned to at most 5 tests per file (121 tests, not 801), so several behaviours named in the acceptance criteria (copies, soft-deleted filters, no half-transaction reads) have no test of their own; I covered the new store's order, case-insensitivity, rollback (existing) and the 20-thread case. Suite: 120 passed; no `fernslop.db` left in `backend/`. Smoke: with no variable and with an explicit URL the app created the file and served `/api/health` and 3 rooms; `python -m app.photo_cleanup` and `digest.main()` ran on it.

**QA:**

## QA: PASS

- [x] `get_store()` reads `FERNSLOP_DATABASE_URL`, default `sqlite:///fernslop.db`; `FERNSLOP_DB_PATH` not read anywhere - PASS
      grep finds no code reading it (only old backlog text). Unset, run from a scratch dir: `/api/rooms` returned 200 with 3 rooms and `./fernslop.db` was created there. With an explicit sqlite URL: `custom.db` created, 3 rooms. `fernslop.db*` is in `.gitignore`.
- [x] `Store` and `sqlite_store.py` deleted; suite uses SQLite URLs only; no `fernslop.db` left - PASS
      `app/sqlite_store.py` is gone, no `class Store`; after `uv run pytest`, `backend/fernslop.db` does not exist.
- [x] Store behaviours (copies, replace keeps position, feed order/ties, case-insensitive email, soft-deleted filters, threads) - PASS
      Dedicated tests exist for replace-position/ties, email case and threads. Copies and soft-deleted filters have no dedicated test; checked directly in a script: mutating a returned room does not change the store; soft-deleted room plants and areas are hidden (3 vs 5, 1 vs 2 with `include_deleted=True`).
- [x] Restart: earlier writes visible incl. byte-identical photo, seed applied once, `reset()` restores it - PASS
      Script on a tmp file URL: edit and a 256-byte photo survived a second `SqlStore`; the edit was not overwritten by a re-seed (still 3 rooms); `reset()` restored the seed and dropped the photo.
- [x] `transaction()` rollback, nesting, thread exclusivity - PASS
      Two saves then raise: both undone, exception propagated. Nested block with outer raising: all undone; nested with no error: committed. `test_twenty_threads_...` exists and passes (20 records, no lock error). Code reads hold the store lock, so no half transaction is visible.
- [x] Portable schema; SQLite-specific code only in connection setup, sqlite-only - PASS
      Read `sql_store.py`: `create_all` with `String`/`Integer`/`Text`/`LargeBinary` only; pragmas, `check_same_thread`, `BEGIN IMMEDIATE`, `StaticPool` are all inside `_make_engine`, which returns a plain engine for non-sqlite dialects.
- [x] `photo_cleanup` and `digest.main()` use the configured DB - PASS
      `FERNSLOP_DATABASE_URL=<scratch file> uv run python -m app.photo_cleanup --hours 0` printed "Deleted 0 photo(s)", exit 0. Photo-deletion count (older and unreferenced only, a single delete statement, count returned) checked via `delete_unreferenced_photos`; `digest.main()` calls `get_store()` and ran on the scratch DB ("Digests sent: 0, failed: 0").

Tests: `uv run pytest`, 120 passed, 0 failed
