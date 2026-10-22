# [audit] Per-IP rate limits on writes, with real client IPs

## Goal

One script can no longer wipe, fill or flood the site: every write is rate limited per client IP in the app, the app and its logs see the real client IP instead of Caddy's, and the UI explains a 429 (`audit.md` 1, 2 and 8 rate-limit parts, 13 last bullet). Decision (user): limits live in the app, in memory, per IP, for the single uvicorn worker (see parked [#090](parked/090-api-live-multi-worker.md)); no new dependency.

## Acceptance criteria

- [ ] Default limits per client IP (IPv6 keyed by its /64), each overridable by an env variable listed in the module docstring: create room 10/hour, delete room 10/hour, upload photo 30/hour, identify 20/hour, follow 10/hour, every other write (plants, care, areas, posts, undo, unfollow) 120/minute.
- [ ] Over a limit the call answers 429 with an `Error` body and a `Retry-After` header in whole seconds, and writes nothing; the limit is checked before the body is read or the store touched. Buckets are separate (the photo limit does not block moving plants) and another IP is unaffected.
- [ ] `GET` requests, `/live` streams and `/api/health` are never limited.
- [ ] Tests are not broken: an autouse fixture in `backend/conftest.py` resets the limiter for every test, an env flag (e.g. `FERNSLOP_RATE_LIMIT=off`) disables it, and the backend and e2e suites pass unchanged.
- [ ] Frontend: a 429 shows a friendly toast such as "You're going a bit fast. Try again in 30 seconds", using `Retry-After` (`httpService.ts`); the mock service never limits.
- [ ] Real client IP: the image runs uvicorn with `--proxy-headers` and `FORWARDED_ALLOW_IPS`. In `infra/ec2-stack.yaml` Caddy gets a fixed address on a fixed compose subnet and only that address is trusted; with nothing trusted (local runs) a client-sent `X-Forwarded-For` is ignored (test). Access logs show the client IP.
- [ ] `openapi.yaml` documents the 429 with `Retry-After` on every limited operation (a shared response).

## Out of scope

- Caps on follows per room and per address: [#207](207-audit-follow-caps.md).
- Getting the compose change onto an already running instance: [#208](208-audit-apply-to-running-instance.md).

## Constraints

- A new `backend/app/rate_limit.py` used as a FastAPI dependency on each write route (an explicit list, no catch-all middleware); the routers; `backend/conftest.py`; `Dockerfile` (CMD); `infra/ec2-stack.yaml`; `frontend/src/services/http/httpService.ts`; `openapi.yaml`.
- Memory stays bounded: expired buckets are dropped, so many distinct IPs cannot grow it without limit. Thread-safe (sync routes run in the thread pool).
- At most 5 tests; follow `_docs/testing-guidelines.md`.
