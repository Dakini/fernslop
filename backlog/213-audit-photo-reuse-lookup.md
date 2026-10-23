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
