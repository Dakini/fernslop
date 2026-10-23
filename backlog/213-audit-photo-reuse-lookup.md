# [audit] Look up "photo already in a post" by URL instead of reading every feed

## Goal

The #199 check in `routers/posts.py` (`_photo_in_a_post`) asks the store one question by `photo_url` instead of reading every room's feed on each photo post, so its cost no longer grows with all feed events on the site.

## Acceptance criteria

- [ ] A photo post runs one `EXISTS`-style query on `feed_events.photo_url` for the check, the same for 3 rooms as for 200 (a test counts the queries, as #202 did); `posts.py` no longer calls `list_rooms` or `list_feed_events`.
- [ ] Same answers as today: the seed photo, a photo in another room's post and a photo in an undone post give 400 `That photo is already in a post` and write nothing; a fresh upload posts (201).
- [ ] New: a photo used by a post in a soft-deleted, not yet purged room (#196) also gives 400 (today it is accepted, because `list_rooms` skips deleted rooms).

## Out of scope

- None.

## Constraints

- `backend/app/store.py` (new protocol method, e.g. `photo_url_in_feed(url) -> bool`), `sql_store.py`, `routers/posts.py`, `test_posts.py`. No new SQL column (parked [#140](parked/140-db-migrations.md)); an index on `feed_events.photo_url` in the table definition is fine (new databases only). At most 2 tests.

**Engineer:** Implemented on branch `worktree-agent-aff7b408c60e5e509` (commit 896da0e).
- `store.py`: one new protocol method, `photo_url_in_feed(url) -> bool`, placed next to the other feed methods. Nothing else in the protocol changed.
- `sql_store.py`: `photo_url_in_feed` runs `SELECT EXISTS(... WHERE feed_events.photo_url = :url)` with no room filter, so undone posts and posts in soft-deleted, not yet purged rooms count. Purge deletes a room's feed rows, so purged rooms no longer block reuse. `feed_events.photo_url` now has `index=True` (`create_all` adds it to new databases only; no new column).
- `routers/posts.py`: removed `_photo_in_a_post`. The post route calls `store.photo_url_in_feed(photo.url)` and no longer calls `list_rooms` or `list_feed_events`.
- Tests (2, in `test_posts.py`): (1) a photo post runs the same number of queries with 3 rooms as with 200 rooms that have posts, and both give 201 (this also covers a fresh upload posting); (2) parametrized over a photo in another room's post, in an undone post and in a soft-deleted room's post: each gives 400 `That photo is already in a post`, the feed is unchanged and nothing is notified. The seed-photo case was already covered by `test_invalid_post_is_400_with_message_and_writes_nothing`. Against the old code, the query-count test and the deleted-room case fail. With the change: `uv run pytest` 170 passed, 2 skipped; `uvx ruff check .` clean.

## QA: PASS

- [x] One `EXISTS`-style query on `feed_events.photo_url`, the same for 3 rooms as for 200; `posts.py` no longer calls `list_rooms` or `list_feed_events` - PASS
      Captured the SQL of a photo post (upload outside the capture). There were 8 statements with 3 rooms and 8 with 203 rooms, on both SQLite and Postgres 16. The check is `SELECT EXISTS (SELECT * FROM feed_events WHERE feed_events.photo_url = ?)`. The only other feed_events read is the save's lookup by id, and every rooms query filters by id, so nothing scans rooms or feeds. `grep` finds no `list_rooms` or `list_feed_events` in `routers/posts.py`. On Postgres, `ix_feed_events_photo_url` is created.
- [x] Same answers as before: the seed photo, a photo in another room's post and a photo in an undone post give 400 `That photo is already in a post` and write nothing; a fresh upload posts (201) - PASS
      Each of the three gave 400 with that exact message, the target room's feed stayed at 13 -> 13 events and `live.notify` was not called. A fresh upload gave 201 and notified. Same results on SQLite and Postgres.
- [x] A photo in a soft-deleted, not yet purged room gives 400 - PASS
      Soft-deleted the room with `delete_room` and confirmed `list_rooms` no longer shows it. Reusing its photo gave 400 `That photo is already in a post`, wrote nothing and sent no notification.

Note (no criterion; the issue does not specify this): after `purge_deleted_rooms` removes that room, the purge also deletes the photo row, because no other event points at it. `photo_url_in_feed` then returns False. Posting the old `photo_id` gives 400 `That photo didn't upload — try again` (the photo is gone), not "already in a post". This matches the engineer's note that purged rooms no longer block reuse.

Tests: `uv run pytest`, 170 passed, 2 skipped, 0 failed. `uvx ruff check .`: all checks passed. On a throwaway Postgres 16 container (unique name, free port, removed afterwards), `FERNSLOP_TEST_DATABASE_URL=... uv run pytest app/test_posts.py app/test_sql_store.py app/test_room_delete.py` gave 32 passed, with the Postgres-only tests included. The `test_posts.py` fixtures use SQLite, so I also ran a spot-check script for each case above against that Postgres.
