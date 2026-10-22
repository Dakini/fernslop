# [db] Support Postgres
## Goal
`FERNSLOP_DATABASE_URL=postgresql+psycopg://user:pw@host/db` works, with the same behaviour as SQLite and the cross-process safety `BEGIN IMMEDIATE` gives SQLite today.
## Acceptance criteria
- [ ] `psycopg[binary]` (v3) is in `backend/pyproject.toml` and `uv.lock` (via `uv add`, user-approved), so `uv sync --frozen --no-dev` installs it and the `Dockerfile` needs no change to use a postgres URL.
- [ ] On an empty Postgres database the tables are created and seeded once; two stores starting at the same moment end with one seed and no error, and a restart does not re-seed.
- [ ] Same behaviour as SQLite on Postgres: insertion order via `seq` (a replaced record keeps its position, feed ties newest-saved first), follow emails match case-insensitively, a photo's `data` comes back byte-identical (bytea), JSON records round-trip.
- [ ] On Postgres `transaction()` is exclusive across separate stores/connections (e.g. a transaction-level advisory lock taken when the outermost transaction begins): two stores on one database, 10 threads each doing read-count-save, end with exactly 20 records and no error. Rollback on exception and nesting still work.
- [ ] SQLite is unchanged: pragmas, `BEGIN IMMEDIATE` and `StaticPool` stay in `_make_engine` and run only for sqlite; Postgres-only code (lock, pool settings such as `pool_pre_ping`) runs only for postgresql.
- [ ] `uv run pytest` passes on SQLite with no setup. With env `FERNSLOP_TEST_DATABASE_URL` set to a postgres URL, `conftest.py` runs the same suite on it (emptied between tests); Postgres-only tests are skipped when it is unset. The command to start a throwaway `postgres` container and run the suite is in `_docs/testing-guidelines.md`.
- [ ] The Docker image, run with `FERNSLOP_DATABASE_URL` pointing at a throwaway postgres container, serves `/api/health` and the seeded `/api/rooms`.
## Out of scope
- Alembic migrations (`create_all` stays): [#140](parked/140-db-migrations.md). Live updates across workers (image stays at one worker): [#090](parked/090-api-live-multi-worker.md). Compose files, serving frontend and API together: [#120](parked/120-api-deploy-together.md).
## Constraints
- Stay in `backend/` (`sql_store.py`, `store.py` docstring, `conftest.py`, `pyproject.toml`), the `Dockerfile` comment and `_docs/testing-guidelines.md`. No other new dependency; `StoreProtocol` gains no method. At most 5 new tests (`_docs/testing-guidelines.md`). Docker is available for the postgres container.
## Original request
**What:** Run the SQLAlchemy store ([#016](done/016-db-sqlalchemy-store.md)) against Postgres: add the driver dependency, run the suite against it, and make `transaction()` exclusive across processes (e.g. row/advisory lock), since SQLite's `BEGIN IMMEDIATE` does that job today.
**Why:** Moved out of #016, which only makes the code database-agnostic and ships SQLite.
**Edge cases:** Ordering by insertion (`seq`), case-insensitive email matching and BLOB/bytea photos must behave the same; connection pool settings.
## Comments
