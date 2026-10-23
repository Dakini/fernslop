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
