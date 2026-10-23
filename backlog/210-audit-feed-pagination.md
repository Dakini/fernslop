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
