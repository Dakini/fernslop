# [db] Replace the in-memory store with a SQLAlchemy database store

## Goal

One `StoreProtocol` implementation on SQLAlchemy replaces the in-memory `Store` and the raw-`sqlite3` `SqliteStore`. Data survives restarts by default, and the database is chosen by a SQLAlchemy URL so Postgres can be added later ([#130](parked/130-db-postgres.md)).

## Acceptance criteria

- [ ] `get_store()` builds the store from env `FERNSLOP_DATABASE_URL`; unset, it uses `sqlite:///fernslop.db` (relative to the working dir, ignored by git, created on first use). `FERNSLOP_DB_PATH` is no longer read anywhere. Routers are unchanged.
- [ ] The in-memory `Store` and `sqlite_store.py` are deleted; `uv run pytest` passes using SQLite URLs (in-memory or `tmp_path`) only, and afterwards no `fernslop.db` exists in the repo.
- [ ] The behaviour tests in `test_store.py` (copies, replace keeps position, feed order incl. ties, case-insensitive email, soft-deleted filters, threads) still pass against the new store.
- [ ] Restart: a new store on the same URL sees earlier writes, incl. a photo with byte-identical `data`; the demo seed is applied once to an empty DB and never again on reopen; `reset()` restores it.
- [ ] `transaction()` rolls back every save/delete if the block raises (exception still propagates), nests with the outermost exit deciding, and is exclusive across threads in one process: 20 threads doing read-count-save end with exactly 20 records, no "database is locked", and no reader sees half a transaction.
- [ ] Portable: the schema is created with `create_all` using only portable SQLAlchemy types (records may stay JSON text next to a few indexed columns); SQLite-specific code (pragma, `BEGIN IMMEDIATE`) lives only in connection setup and runs only when the dialect is sqlite.
- [ ] `python -m app.photo_cleanup [--hours N]` and `digest.main()` use the configured DB (no env var required any more); cleanup keeps its behaviour from [#015](done/015-api-persistence.md) (older, unreferenced photos only; one transaction; prints the count).

## Out of scope

- Postgres driver, running the suite on it and cross-process `transaction()` locking: [#130](parked/130-db-postgres.md). Alembic migrations: [#140](parked/140-db-migrations.md).
- Importing data from an existing `FERNSLOP_DB_PATH` file: not planned.

## Constraints

- Stay in `backend/`: `store.py`, a new SQLAlchemy store module, `photo_cleanup.py`, `digest.py`, `conftest.py`, `.gitignore`. `StoreProtocol` gains no required method.
- Add `sqlalchemy` with `uv add` (user-approved); no other new dependency. At most 5 new tests (adapting or moving existing ones is free); follow `_docs/testing-guidelines.md`.

## Original request

**What:** Replace `Store` (in-memory) and the raw-`sqlite3` `SqliteStore` ([#015](done/015-api-persistence.md)) with one `StoreProtocol` implementation on SQLAlchemy, SQLite by default. The database is chosen by one environment variable holding a SQLAlchemy URL (replaces `FERNSLOP_DB_PATH`), and nothing outside the connection setup may be SQLite-specific, so Postgres can be added later ([#130](parked/130-db-postgres.md)). Routers stay untouched. **Why:** The user asked for a real database via SQLAlchemy that is database-agnostic; today the default store loses all data on restart and the persistent one is stdlib-only and SQLite-bound. Adding the `sqlalchemy` dependency is explicitly approved by the user. **Edge cases:** `transaction()` must stay atomic, re-entrant and exclusive under threads (undo and 50-plant limit checks, see #015); photos (bytes), `undo_payload`, insertion order, feed-order ties and case-insensitive follow emails must behave as before; seed once on an empty DB, `reset()` restores it; `photo_cleanup` and `digest.main()` must use the configured DB; tests must not touch a developer's real DB file; schema is created with `create_all` (migrations are [#140](parked/140-db-migrations.md)).
