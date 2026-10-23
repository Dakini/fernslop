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

## Comments

**Engineer:** Implemented in `9d524c6` (backend) and `f9745ca` (spec/frontend). Backend: `GET /api/rooms` now returns `{rooms, next}`. It takes `limit` (default 30, 1-100; anything else, including non-numbers, is a 400) and `before`, a keyset cursor `<last_activity_at>_<created_at>_<id>` built from the fixed-width timestamps (a malformed cursor is a 400). The router reads every live room with the existing `store.list_rooms()` (one query; #196's `_live_rooms` still drops deleted rooms, so they are never listed or counted), sorts in Python by (activity, created, id) descending, cuts the page, then fetches only that page's room plants, their plants and their areas with three new bulk reads (`get_plants`, `list_room_plants_in`, `list_areas_in` in `sql_store.py`, added to `StoreProtocol`). That makes 4 queries per request whatever the room count. `next` is the last row's cursor, or null on the last page. `GET /api/plants/search` stops after `DEFAULT_SEARCH_LIMIT` (12) matches, in table order. `openapi.yaml`: `listRooms` has the `limit`/`before` params, a 400, and a new `RoomPage` schema; `searchPlants` documents the 12 cap. Frontend: `GardenService.listRooms({before, limit})` returns a `RoomPage`. The HTTP service sends the query string, and the mock pages with the same cursor, the same limits and the 12-match search cap. The index uses `useSuspenseInfiniteQuery` and shows a `soft` "Show more gardens" button (task-named label, as `_docs/design-system.md` says) only while `next` is set. Rooms from all loaded pages are de-duplicated by id, so a room that moved between pages shows once. A live refetch (`invalidateQueries(["rooms"])`) reloads as many pages as were loaded, because TanStack refetches infinite queries page by page. **Deviation:** `roomsQuery` lives in `frontend/src/lib/queries.ts`, which the issue does not list. I changed it there to `infiniteQueryOptions` (the index was its only user) and did not copy it into `index.tsx`. Tests (5): `test_rooms.py` has a query count that is the same for 3 and 200 rooms, paging with `limit=2` through all rooms while skipping a deleted one and ending with `next: null`, and 400s for `limit=0/101/ten` and a bad cursor. `test_plants.py` checks that `q=a` returns the first 12 matches. `mockService.test.ts` checks that the mock pages and rejects `limit: 101`. I updated the existing list assertions in `test_rooms.py`/`test_room_delete.py`/`mockService.test.ts` to read `.rooms`. Results: `uv run pytest` 158 passed, 2 skipped. `uvx ruff check .` is clean. `npm test` 42 passed. `npm run build` OK, and `tsc` shows no errors in the touched files (the existing errors elsewhere are unchanged). I did not check the button in a browser.

## QA: PASS

- [x] `GET /api/rooms` runs the same number of SQL queries for 3 rooms as for 200 - PASS
      TestClient + SQLAlchemy `before_cursor_execute` counter: 8 statements for the 3 seed rooms and 8 for 200 rooms (66 with plants), i.e. one SELECT each on rooms, room_plants, plants, areas plus their BEGINs; nothing per room. Covered by `test_list_rooms_runs_as_many_queries_for_200_rooms_as_for_3`.
- [x] At most `limit` rooms (default 30, max 100, else 400), newest activity first, `next` cursor, `next: null` on the last page - PASS
      200 rooms: default page 30 with a cursor, `limit=100` gives 100, `limit=1` gives 1; walking `limit=7` with `before` gave 29 pages, 200 unique rooms, last page 4 with `next: null`; activity sorted descending. `limit=0/101/-1/ten/(empty)/1.5` and `before=junk`/`before=a_b` all 400.
- [x] Soft-deleted rooms are never listed and do not count towards a page - PASS
      Deleted the 5 newest rooms: a full walk listed 195 with none of them; `limit=10` still returned 10, starting with the next live room.
- [x] Index shows the first page and "Show more gardens", which appends the next page, hides on the last, shows a moved room once, keeps loaded pages on refetch - PASS
      Static build served by this worktree's backend on :8402 with 45 rooms, Playwright at 1280x800 and 390x844: 30 cards in API order and a soft pill button (no horizontal overflow); click appended to 45/46 unique cards in API order and the button disappeared. Loaded both pages, added a plant to a room on page 2 via the API, went into a room and back: 45 cards, that room first and shown once. Bumped a page-2 room after page 1 loaded, then Show more and refetch: 45 unique, the room once at the top. Search box filters ("QA Garden 07" gives 1, no match shows the "No gardens match" line); creating a room in the dialog opens `/r/<id>` and it is first on the index. No console errors.
- [x] `GET /api/plants/search?q=…` returns at most 12 matches in today's order - PASS
      `q=a` (50 matches) and `q=e` gave 12, equal to the first 12 matches in `/api/plants` order; `q=rose` gave 3, empty `q` gave 12, `q=zzzz` gave 0.
- [x] `openapi.yaml`, `GardenService`, HTTP service and mock agree; the mock pages the same way - PASS
      Read the code: `listRooms` has `limit`/`before`, a 400 and a `RoomPage {rooms, next}` schema; `searchPlants` documents the 12 cap. `GardenService.listRooms({before, limit}): Promise<RoomPage>`, the HTTP service sends the same query string, and the mock uses the same `activity_created_id` cursor, default 30, max 100 (rejects anything else) and the 12-match search cap. The mock deletes rooms outright, so it never lists them.

Tests: `cd backend && uv run pytest`, 158 passed, 2 skipped, 0 failed; `cd frontend && npm test`, 42 passed, 0 failed. `FERNSLOP_STATIC=1 npm run build` OK.
