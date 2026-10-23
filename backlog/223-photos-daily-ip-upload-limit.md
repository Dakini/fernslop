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

## QA: PASS

- [x] `POST /api/photos` hourly + daily, 429 with `TOO_FAST_MESSAGE` and `Retry-After`, hourly checked first - PASS
      Default limits, TestClient from one IP: uploads 1-15 got 201 and the 16th got 429 `Retry-After: 86400`, "You're going a bit fast. Try again in 86400 seconds.". With `upload_photo=1/hour` and `upload_photo_daily=2/day`, the results were 201, then 429 (3600), then 429 (3600). The limiter's `upload_photo_daily` window count stayed at 1, so hourly rejections are not counted. With the daily limit used up and the hourly limit not, a `text/plain` non-multipart body still got 429, so the limit runs before the body is read.
- [x] `POST /api/plants/identify` the same with 20/hour + 20/day - PASS
      Default limits: calls 1-20 got 200 and the 21st got 429 (3600). Both defaults are 20, so the hourly limit trips first, which is what the spec's hourly-first order means. With `identify=100/hour`, the 21st call got 429 `Retry-After: 86400` with `TOO_FAST_MESSAGE`, and a body-less call then also got 429. The hourly-first test with `identify=1/hour` and `identify_daily=2/day` gave 200, 429, 429, and the daily count stayed at 1.
- [x] Env overrides and `FERNSLOP_RATE_LIMIT=off` - PASS
      With `FERNSLOP_RATE_LIMIT_UPLOAD_PHOTO_DAILY=2/day` set, uploads gave 201, 201, then 429 (86400). With `FERNSLOP_RATE_LIMIT_IDENTIFY_DAILY=2/day`, identify gave 200, 200, then 429 (86400). Adding `FERNSLOP_RATE_LIMIT=off` let 4 more uploads and 4 more identify calls through from the same IP.
- [x] Other IPs and buckets unaffected; no frontend change - PASS
      After IP A used up both daily limits, IP B (TestClient client address) got 201 on upload and 200 on identify. The diff touches no file under `frontend/`.
- [x] `rate_limit.py` docstring and `openapi.yaml` `TooManyRequests` list both daily limits - PASS
      The docstring lists `upload_photo_daily` 15/day and `identify_daily` 20/day with their env names. `TooManyRequests` says "uploadPhoto 30/hour and 15/day, identifyPlant 20/hour and 20/day" and gives the hourly-first rule. The `uploadPhoto` and `identifyPlant` descriptions match what the server does.

Tests: `cd backend && uv sync && uv run pytest` gave 181 passed and 2 skipped. `uvx ruff check .` passed all checks.
E2E: built the frontend (`FERNSLOP_STATIC=1 npm run build`) and ran a local uvicorn on a free port (59822) with SQLite and the default limits. `FERNSLOP_RATE_LIMIT` was unset. `E2E_BASE_URL=http://127.0.0.1:59822 uv run pytest` in `e2e/` gave 4 passed with no 429 in the server log. The server was stopped afterwards.
Note (not a failure): each e2e run makes 2 photo uploads, so a long-running local backend reached from one IP allows about 7 runs before the 15/day upload limit trips. Restarting the server resets it, and the default e2e mode starts a fresh stack each time.
