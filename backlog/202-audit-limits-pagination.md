# [audit] Bound room listing and plant search

## Goal

The index stays fast as rooms pile up: `GET /api/rooms` runs a fixed number of queries and returns one page at a time, and plant search returns at most 12 results (`audit.md` 8 non-rate-limit parts, 14 last bullet). Decision: no cap on rooms per device, because creating a room sends no device id and a device id is free to change; the per-IP limit in #195 covers mass creation.

## Acceptance criteria

- [ ] `GET /api/rooms` runs the same number of SQL queries for 3 rooms as for 200 (one per table, no per-room query); a test counts them.
- [ ] It returns at most `limit` rooms (default 30, at most 100, anything else 400), most recent activity first as today, plus a cursor for the next page (e.g. `{rooms, next}` with `?before=<next>`); the last page has `next: null`.
- [ ] Soft-deleted rooms (#196) are never listed and do not count towards a page.
- [ ] The index page shows the first page and a "Show more gardens" button that appends the next one and is hidden on the last page; a room that moved between pages appears once; a live refetch keeps the pages already loaded.
- [ ] `GET /api/plants/search?q=…` returns at most 12 matches (`DEFAULT_SEARCH_LIMIT`), in today's order.
- [ ] `openapi.yaml` (`listRooms`, `searchPlants`), `GardenService`, the HTTP service and the mock agree; the mock pages the same way.

## Out of scope

- A bounded room feed with "load older", and a cap on posts per room: [#210](210-audit-feed-pagination.md).
- Per-IP limits on room creation: [#195](195-audit-rate-limit.md).

## Constraints

- `backend/app/routers/rooms.py`, `routers/plants.py`, `sql_store.py`/`store.py` (bulk reads), `openapi.yaml`, `frontend/src/services/`, `frontend/src/routes/index.tsx`; button per `_docs/design-system.md`.
- `last_activity_at` lives in the JSON column (no SQL column, migrations parked [#140](parked/140-db-migrations.md)): reading all room rows in one query and sorting in Python is acceptable; plants and areas are fetched only for the rooms on the page.
- After #196. At most 5 tests.
