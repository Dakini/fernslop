# [db] Follow-up: support Postgres
**What:** Run the SQLAlchemy store ([#016](../done/016-db-sqlalchemy-store.md)) against Postgres: add the driver dependency, run the suite against it, and make `transaction()` exclusive across processes (e.g. row/advisory lock), since SQLite's `BEGIN IMMEDIATE` does that job today.
**Why:** Moved out of #016, which only makes the code database-agnostic and ships SQLite.
**Edge cases:** Ordering by insertion (`seq`), case-insensitive email matching and BLOB/bytea photos must behave the same; connection pool settings.
