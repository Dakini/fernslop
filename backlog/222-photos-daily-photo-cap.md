# [photos] Daily cap on photo posts per garden

## Goal

One garden can't fill the 4 GiB photo store (#198) by posting photos. It takes at most `FERNSLOP_PHOTO_POSTS_PER_DAY` (default 15, about 27 MB at #209 sizes) photo posts in any 24 hours. This works like #210's post cap and sits under it. Size: medium, single issue. The engineer implements it and QA spot-checks.

## Acceptance criteria

- [ ] In one room, the 31st post with a `photo_id` within 24 hours gets 429. It uses `TOO_FAST_MESSAGE` from `rate_limit.py` and has a `Retry-After` header with the seconds until the oldest photo post in the window turns 24 hours old. Nothing is written, and the uploaded photo stays unposted, so the 6-hour cleanup removes it.
- [ ] Undone photo posts count, because their bytes stay until the room is purged. Text-only posts, care, plant and area events don't count, and posts in other rooms are not affected. A text-only post in a room that is at the photo cap still gets 201, until the room hits #210's cap of 200.
- [ ] Setting `FERNSLOP_PHOTO_POSTS_PER_DAY=2` caps the room at 2. The value is read on each request, the same way as `FERNSLOP_PHOTO_STORAGE_LIMIT_BYTES`. `FERNSLOP_RATE_LIMIT=off` does not turn this cap off, and it does not turn off #210's cap either.
- [ ] `POST /api/photos` (no room) and `POST /api/identify` (stores nothing) behave as before. The mock never caps. In the browser, the 429 shows only the single `RateLimitError` toast, with no frontend change.
- [ ] `openapi.yaml` describes the cap and its env var in `postUpdate`'s 429, next to where the storage limit is documented.

## Out of scope

- Moving photos to object storage: parked [#205](parked/205-audit-photo-object-storage.md) (the user decided against it for now).
- A daily per-IP upload bucket. The 30/hour limit allows about 720 uploads a day across gardens, and room creation allows 10 gardens an hour. See open question 2.

## Constraints

- Change only `backend/app/routers/posts.py`, `store.py`/`sql_store.py` and `openapi.yaml`. Count photo posts with the indexed `feed_events.photo_url IS NOT NULL` column, in one `COUNT`/`MIN` query like `count_posts_since`, with no JSON match and no new column. Check the cap inside the existing transaction, only when `photo_id` is present.
- Write at most 2 tests, in `backend/app/test_posts.py`, per `_docs/testing-guidelines.md`. One covers cap → 429, `Retry-After` and nothing written, with an undone post counting. The other covers a text-only post still getting 201 at the cap.

## Open questions (recommended default in bold)

1. Default cap: **15 photo posts per garden per day** (user decision, 2026-10-23).
2. Daily per-IP upload limit: the user wants it, filed as a separate follow-up issue.
