# [photos] Daily per-IP limit on photo uploads and identify

## Goal

One client IP can't upload more than `upload_photo_daily` photos (default **15/day**) or call identify more than `identify_daily` times (default **20/day**). Today's hourly buckets from #195 still allow about 720 uploads a day, and #222's 15-per-garden cap can be spread over 10 new gardens an hour. Size: medium, single issue. The engineer implements it and QA spot-checks.

## Acceptance criteria

- [ ] `POST /api/photos` has two limits: the existing `upload_photo` (30/hour) and a new `upload_photo_daily` (15/day). Past either one it gets 429 with `TOO_FAST_MESSAGE` and `Retry-After`. The hourly limit is checked first, so a call it rejects doesn't count against the daily one.
- [ ] `POST /api/plants/identify` works the same way, with `identify` (20/hour) and a new `identify_daily` (20/day). A Pl@ntNet key allows about 500 calls a day for the whole server, and today one IP can make 480.
- [ ] `FERNSLOP_RATE_LIMIT_UPLOAD_PHOTO_DAILY=2/day` and `FERNSLOP_RATE_LIMIT_IDENTIFY_DAILY=2/day` change the new limits through the existing `env_name()` pattern. `FERNSLOP_RATE_LIMIT=off` turns them off along with the others.
- [ ] Other IPs and other buckets are not affected. The mock never limits, and the browser shows only the single `RateLimitError` toast, with no frontend change.
- [ ] The bucket list in the `rate_limit.py` docstring and the `TooManyRequests` response in `openapi.yaml` both list the two daily limits.

## Out of scope

- Per-garden photo cap: #222 (in progress).
- Sliding or persistent windows. Counts are in memory, so they reset when the server restarts, the same as #195.

## Constraints

- Change only `backend/app/rate_limit.py`, `routers/photos.py`, `routers/plants.py` and `openapi.yaml`. The limiter keeps one fixed window per `(bucket, IP)`, so add two new buckets to `DEFAULT_LIMITS` rather than giving one bucket two windows. Each route lists `rate_limited(<hourly>)` and then `rate_limited(<daily>)`, both before `read_upload_file`. Don't change `RateLimiter`.
- Write at most 2 tests, in `backend/app/test_rate_limit.py`, per `_docs/testing-guidelines.md`. One sets `upload_photo_daily=2/day`, sends a 3rd upload, and checks the 429 with a `Retry-After` close to 86400. The other covers `FERNSLOP_RATE_LIMIT=off` letting that 3rd upload through.

## Open questions (recommended default in bold)

1. Daily upload limit: **15/day per IP** (user decision, 2026-10-23). A fixed window starts at the first upload of the day.
2. Daily identify limit: **20/day per IP** (user decision, 2026-10-23).

## Comments

**Engineer:** Implemented. `rate_limit.py` gets two new buckets in `DEFAULT_LIMITS`: `upload_photo_daily` (15/day) and `identify_daily` (20/day). Both are overridable through `env_name()` (`FERNSLOP_RATE_LIMIT_UPLOAD_PHOTO_DAILY`, `FERNSLOP_RATE_LIMIT_IDENTIFY_DAILY`) and turned off by `FERNSLOP_RATE_LIMIT=off`. `RateLimiter` is unchanged. The docstring bucket list now names both, with a note on the order. `routers/photos.py` lists `rate_limited(UPLOAD_PHOTO), rate_limited(UPLOAD_PHOTO_DAILY)` and `routers/plants.py` lists `rate_limited(IDENTIFY), rate_limited(IDENTIFY_DAILY)`. These are route `dependencies`, so they run before the `read_upload_file` parameter dependency. In `openapi.yaml`, the `TooManyRequests` text lists the daily limits and the hourly-first rule, and the `uploadPhoto` and `identifyPlant` descriptions each gain one line naming their limits. The postUpdate 429 is untouched (#222). There is no frontend change. Two tests are in `test_rate_limit.py`: the 3rd upload at `upload_photo_daily=2/day` gets 429 with Retry-After in (86300, 86400], and `FERNSLOP_RATE_LIMIT=off` lets it through. Checks: `uv run pytest` gives 181 passed and 2 skipped, `uvx ruff check .` is clean, and `openapi.yaml` parses. A manual run with upload_photo=1/hour and upload_photo_daily=2/day gave 201, 429, 429, and the daily window count stayed at 1, so hourly rejections are not counted against the daily limit.
