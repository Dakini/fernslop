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

## Comments

**Engineer:** `SqlStore.list_feed_page` in `backend/app/sql_store.py` now writes the keyset as one row-value comparison, `tuple_(c.created_at, c.seq) < tuple_(anchor.created_at, anchor.seq)`, in place of the `or_`/`and_` form. `or_` and `and_` were only used there, so their imports are gone and `tuple_` is imported. No API, schema, index or test change.

Checks:
- SQLite: `uv run pytest` gives 179 passed, 2 skipped (the Postgres-only tests).
- Postgres 17 (throwaway container `fernslop-pg217-eng` on :55417, removed afterwards): `FERNSLOP_TEST_DATABASE_URL=postgresql+psycopg://… uv run pytest` gives 181 passed, including the `test_rooms.py` paging tests (equal timestamps with events arriving, cursor from another room or unknown, bad limit).
- `uvx ruff check .` from `backend/`: all checks passed.

EXPLAIN on Postgres 17: 20 000 events in room `big` (timestamps shared in pairs) plus 20 000 in another room, `ANALYZE`d, cursor at depth 10 000, `limit=50`. The SQL is what `list_feed_page` emitted, captured with a `before_cursor_execute` listener:

```
SELECT feed_events.json FROM feed_events
WHERE feed_events.room_id = %(room_id_1)s::VARCHAR
  AND (feed_events.created_at, feed_events.seq) < (%(param_1)s::VARCHAR, %(param_2)s::INTEGER)
ORDER BY feed_events.created_at DESC, feed_events.seq DESC LIMIT %(param_3)s::INTEGER

Limit  (cost=0.41..7.04 rows=50 width=40) (actual rows=50 loops=1)
  ->  Index Scan Backward using ix_feed_events_room_created_seq on feed_events  (cost=0.41..1320.42 rows=9966 width=40) (actual rows=50 loops=1)
        Index Cond: (((room_id)::text = 'big'::text) AND (ROW((created_at)::text, seq) < ROW('2026-01-01T01:23:20.000000+00:00'::text, 10022)))
Planning Time: 0.061 ms
Execution Time: 0.043 ms
```

For comparison, the old `OR` form on the same data and cursor:

```
Limit  (cost=0.41..10.49 rows=50 width=40) (actual rows=50 loops=1)
  ->  Index Scan Backward using ix_feed_events_room_created_seq on feed_events  (cost=0.41..2009.54 rows=9966 width=40) (actual rows=50 loops=1)
        Index Cond: ((room_id)::text = 'big'::text)
        Filter: (((created_at)::text < '2026-01-01T01:23:20.000000+00:00'::text) OR (((created_at)::text = '2026-01-01T01:23:20.000000+00:00'::text) AND (seq < 10022)))
        Rows Removed by Filter: 10000
Execution Time: 2.377 ms
```

## QA: PASS

- [x] On Postgres 17, `EXPLAIN ANALYZE` of a page at depth 10 000 of 20 000 shows the keyset as an `Index Cond` on `ix_feed_events_room_created_seq`, with no `Rows Removed by Filter` for it - PASS
      Throwaway `postgres:17` (17.11) container `fernslop-pg217-qa` on :55517, removed afterwards. Ran the engineer's script (it only uses the URL it is given): 20 000 events in `big` (pairs share a timestamp) plus 20 000 in `other`, `ANALYZE`d, cursor at depth 10 000, `limit=50`, SQL captured from `list_feed_page` itself:
      `Index Scan Backward using ix_feed_events_room_created_seq` with
      `Index Cond: (((room_id)::text = 'big'::text) AND (ROW((created_at)::text, seq) < ROW('2026-01-01T01:23:20.000000+00:00'::text, 10022)))`,
      actual rows=50, no `Filter` line and no `Rows Removed by Filter`, execution 0.031 ms. Cross-check in psql: the 50 keyset rows equal `OFFSET 10000 LIMIT 50` under the same ordering, across the shared-timestamp boundary.
- [x] Paging results are unchanged: the `test_rooms.py` paging tests pass on SQLite and on Postgres - PASS
      `test_feed_pages_cover_equal_timestamps_without_gaps_or_repeats_while_events_arrive` and `test_feed_page_with_a_cursor_from_another_room_or_a_bad_limit_gives_400` both pass on SQLite and with `FERNSLOP_TEST_DATABASE_URL` pointing at the container (`conftest.py` switches the fixtures' store to it).
- [x] `uvx ruff check .` is clean - PASS ("All checks passed!" from `backend/`)

Tests: `uv sync && uv run pytest` (SQLite): 179 passed, 2 skipped (Postgres-only). `FERNSLOP_TEST_DATABASE_URL=postgresql+psycopg://…:55517/fernslop uv run pytest`: 181 passed, 0 failed.

The diff touches only `list_feed_page` in `backend/app/sql_store.py` (and the imports). No code was changed by QA.
