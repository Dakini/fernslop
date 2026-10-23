# [audit] Bounded room feed with "Load older", and a daily post cap per room

## Goal

A room with a huge feed stays usable: its state response carries only the newest feed events, older ones load on demand, and one room cannot gain more than 200 posts a day (`audit.md` 8, moved out of #202). Follows #202's paging pattern (`{…, next}` with `?before=`).

## Acceptance criteria

- [ ] `GET /api/rooms/{id}` returns at most the newest 50 feed events plus `feed_next`, the cursor for older ones (null when there are none); everything else in the state is unchanged.
- [ ] A new `GET /api/rooms/{id}/feed?before=<cursor>&limit=<n>` (default 50, 1–100, else 400; a malformed cursor 400; unknown or soft-deleted room 404) returns `{events, next}`, newest first, continuing exactly where the cursor left off: no gap or repeat with events sharing a `created_at`, or when new events arrive in between. Reading a page does not load the whole feed.
- [ ] The Feed tab shows a "Load older" button that appends the next page and is hidden on the last one; a live refetch keeps the older pages loaded and shows new events at the top once.
- [ ] Undo on an event from an older page works, and the event then shows as undone without a reload.
- [ ] The 201st post in one room within 24 hours (undone posts count; care, plant and area events do not) answers 429 with an `Error` body and `Retry-After`, and writes nothing.
- [ ] `openapi.yaml` (`getRoomState`, the new operation, `postUpdate`'s 429), `GardenService`, the HTTP service and the mock agree; the mock pages the same way and never caps.
- [ ] Tests: paging across equal timestamps without gaps or repeats; the post cap.

## Out of scope

- The browser's wording for long waits (`Try again in N hours`): [#214](214-audit-rate-limit-double-toast.md).

## Constraints

- `backend/app/routers/rooms.py`, `routers/posts.py`, `models.py` (`RoomState`), `store.py`/`sql_store.py` (a paged read ordered by `created_at`, `seq` with `LIMIT`; a post count bounded by `created_at`, no new SQL column), `openapi.yaml`, `frontend/src/services/`, `lib/queries.ts`, `routes/r.$roomId.tsx`. Button per `_docs/design-system.md`.
- The digest and #201's "later event" check keep reading the store, not a page. After #213 (same `posts.py`/store files). At most 5 tests.

## Comments

**Engineer:** Backend: `RoomState` now has `feed_next` and carries the newest 50 events. The new `GET /api/rooms/{id}/feed?before=&limit=` (`getRoomFeed`, in `routers/rooms.py`) returns `{events, next}`. The cursor is the id of the last event on the page. A cursor this room never gave out, or a limit outside 1–100, is a 400, and an unknown or soft-deleted room is a 404. `SqlStore.list_feed_page` does keyset paging on (`created_at`, `seq`) with `LIMIT`, so it reads one page, not the whole feed. A new index `ix_feed_events_room_created_seq` covers it on existing columns. It is created with `checkfirst` so existing databases get it too, and there is no new column. `list_feed_events` stays as it was for the digest and #201's "later event" check. Post cap: `count_posts_since` is one `COUNT`/`MIN` query over the last 24 hours, matching `"type":"post"` in the JSON. Undone posts count; care, plant and area events do not. `post_update` checks it inside the transaction. At 200 it answers 429 with `TOO_FAST_MESSAGE` from `rate_limit.py` and `Retry-After` set to the time until the oldest post in the window turns 24 hours old. Nothing is written in that case. `openapi.yaml`: `getRoomState` text, `RoomState.feed_next`, the new `FeedPage` schema and `getRoomFeed` operation, and `postUpdate`'s 429 with `Retry-After`. Frontend: `types.ts` (`FeedPage`, `feed_next`, `GardenService.getRoomFeed`), the HTTP service and the mock now page the same way. The mock sorts by `created_at`, then save order, uses the id as the cursor and has no cap. `lib/queries.ts` adds `olderFeedQuery` and `useRoomFeed`. Older pages always start at the state's *current* `feed_next`. Every time the room state refetches (a live update, your own write or an undo), the loaded older pages refetch too, and the events are de-duplicated by id. As a result older pages stay loaded, new events show at the top once, and an undo on an older page shows as "Undone" without a reload. In `routes/r.$roomId.tsx` I only changed the Feed tab list, which is now a `FeedList` component next to `GardenDeleted` with a secondary "Load older" button, plus the `queries` import line. PostBox and photo upload are untouched. I also ran `ruff --fix` on import order in `test_sql_store.py` and `conftest.py`, which already failed `uvx ruff check .`. Tests (4): equal-timestamp paging with an event arriving in between, the cursor/limit/404 errors, and the post cap in the backend; mock paging in the frontend. I changed the existing mock test "won't undo a removal into a full room" to read the store, because its event is now past the newest 50. Checks: `uv run pytest` passed (180, 2 skipped), `uvx ruff check .` is clean, `npm test` passed (51), and `FERNSLOP_STATIC=1 npm run build` succeeded. I ran a Playwright check against a local uvicorn on a free port (:54233) with a scratch SQLite DB, serving the built frontend. The room had 121 events. The Feed tab showed 50, then 100, then 121 rows, the posts were in exact order with no repeats, and "Load older" was hidden on the last page. Undo on the oldest event (on the 3rd page) showed "Undone" with all 121 rows kept. A post from another device arrived live at the top, once (122 rows, older pages still there). At 375px there was no horizontal overflow, and the console had no errors. On the same server, posts up to 200 were accepted and the 201st got 429 with `Retry-After: 86386`. The server is stopped. Issue left open.

## QA: PASS

- [x] `GET /api/rooms/{id}` returns the newest 50 plus `feed_next` - PASS
      I tested a room with 137+ events. The keys are exactly `room, plants, areas, feed, feed_next`, the feed has 50 events and `feed_next` is set. A new room with no events gives `feed_next: null` and an empty feed.
- [x] `GET /api/rooms/{id}/feed` with paging, bounds and errors - PASS
      The room had 137 events in runs of 13 that share a `created_at`. I walked it with `limit=11` (8 pages). After the first page I added 3 live posts and one event with an old timestamp. Every original event came back exactly once and in store order. The new posts did not appear, which is correct because they are newer than the cursor. The old-stamped event appeared once, in its place. A fresh walk with the default limit (2 pages) matched the store exactly. `limit` 1 and 100 give 200. `limit` 0, 101, -1, `abc`, `5.5` and an empty value each give 400 with an `Error` body. A bad cursor and a cursor from another room each give 400. An unknown room, a non-uuid room and a soft-deleted room (with or without a cursor) each give 404.
      Postgres 17 (throwaway container): `uv run pytest` gives 180 passed. The index `ix_feed_events_room_created_seq (room_id, created_at, seq)` exists. When I dropped it and reopened the store, it was recreated on the existing database. The page query is a backward index scan with `LIMIT 51` that returns 51 rows, not the whole feed.
      Non-blocking finding: the `OR` keyset predicate is a Filter, not an Index Cond. So a deep cursor scans every newer index entry of the room: at position 10 000 of 20 000 it removed 10 001 rows and took 1.3 ms. A row-value predicate `(created_at, seq) < (:c, :s)` becomes an Index Cond on Postgres.
- [x] Feed tab "Load older" button, and live refetch - PASS
      Playwright (Chromium) ran against a local uvicorn on :58710 with a scratch SQLite DB, the static build and rate limits off. The room had 130 events. The row counts went 50, 100, 130, and "Load older" was hidden after the last page. The 130 UI rows matched the API order. I then posted from a second browser context while all pages were loaded. The post arrived at the top once (131 rows), and the older pages stayed loaded. My own post from the first browser also showed once (132 rows).
- [x] Undo on an event from an older page - PASS
      I clicked Undo on the oldest row ("added a Basil", on the 3rd page). It showed "Undone" without a reload, and all 130 rows stayed.
- [x] 201st post within 24 hours gives 429 - PASS
      Through the API, the room had one undone post 23.5 hours old, one post 24 hours 5 minutes old, and 43 care, plant and area events. One care event's text contained `"type":"post"`. Posts 2 to 200 were all 201. The 201st was 429 with `{"message":"You're going a bit fast. Try again in 1800 seconds."}` and `Retry-After: 1800`, which matches the time until the undone post turns 24 hours old. The feed row count (244 before and after) and the room row were unchanged. In the capped room the 202nd post was still 429, but adding a plant was 201. A post in another room was 201.
- [x] `openapi.yaml`, `GardenService`, the HTTP service and the mock agree - PASS
      They agree on these points:
      - `getRoomState` text, `RoomState.feed_next` (required, nullable) and `maxItems: 50`
      - the `FeedPage` schema and the `getRoomFeed` operation: `before`, `limit` 1–100 with default 50, and the 400 and 404 responses
      - `postUpdate`'s 429 with `Retry-After`
      `types.ts` has `FeedPage`, `feed_next` and `getRoomFeed(roomId, {before, limit})`. The HTTP service builds `?limit=&before=`. The mock sorts by `created_at` and then save order, uses the event id as the cursor, enforces `limit` 1–100, rejects an unknown cursor and has no cap. The mock test posts 230 times.
- [x] Tests for equal-timestamp paging and the post cap - PASS
      These are in `test_rooms.py` (paging with equal timestamps and an event arriving in between, and the 400/404 errors), `test_posts.py` (the cap) and `mockService.test.ts`.

Tests:
- `cd backend && uv sync && uv run pytest`: 178 passed, 2 skipped (SQLite).
- The same suite on Postgres 17 with `FERNSLOP_TEST_DATABASE_URL`: 180 passed.
- `uvx ruff check .` from the repo root passes.
- `cd frontend && npm test`: 51 passed.
- `FERNSLOP_STATIC=1 npm run build` succeeded.

Findings (non-blocking):
- `uvx ruff check .` run from inside `backend/` now reports 2 I001 errors in `app/test_sql_store.py` and `conftest.py`. The engineer's `ruff --fix` was run from the repo root, where `conftest` sorts as third-party. Before this change those files passed from `backend/`, and they pass from the root now.
- The deep-page Postgres scan described under the second criterion.
- `_docs/design-system.md` is still the outdated Django note. The button uses the app's existing `Button variant="secondary"`, and at 375px it is full width (319×32) with no horizontal overflow.
