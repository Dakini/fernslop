# [qa] Feed paging bounds the index scan on Postgres

## Goal

A deep "Load older" page reads only its own rows on Postgres: `SqlStore.list_feed_page` compares `(created_at, seq) < (:c, :s)` as a row value (SQLAlchemy `tuple_`) instead of the `OR` form, so the index bounds the scan (QA finding on [#210](done/210-audit-feed-pagination.md)). Small.

## Acceptance criteria

- [ ] On Postgres 17, `EXPLAIN ANALYZE` of a page at depth 10 000 of 20 000 shows the keyset as an `Index Cond` on `ix_feed_events_room_created_seq`, with no `Rows Removed by Filter` for it.
- [ ] Paging results are unchanged: the existing `test_rooms.py` paging tests (equal timestamps, an event arriving in between, an unknown or other-room cursor) pass on SQLite and with `FERNSLOP_TEST_DATABASE_URL` on Postgres.
- [ ] `uvx ruff check .` is clean.

## Out of scope

- None.

## Constraints

- `backend/app/sql_store.py` (`list_feed_page` only). No API, schema or index change.
- No new tests (the existing paging tests cover it); the engineer pastes the `EXPLAIN` output in the comment.
