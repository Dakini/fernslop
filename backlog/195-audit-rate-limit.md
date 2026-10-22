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

**User decision (2026-10-22):** the PM default numbers are approved as written (all overridable by env).

## Comments

**Engineer:** New `backend/app/rate_limit.py`: an in-memory, fixed-window limiter keyed by bucket and client IP (IPv6 by its /64, IPv4-mapped IPv6 as IPv4). It is guarded by a lock, and expired windows are swept at most once a second. Defaults are the approved PM numbers. Each one can be changed with `FERNSLOP_RATE_LIMIT_<BUCKET>` (`10/hour` style); the module docstring lists them. `FERNSLOP_RATE_LIMIT=off` turns all limits off. Every write route lists `dependencies=[rate_limited(...)]` (15 routes, no middleware). GET routes, `/live` and `/api/health` are untouched. Over a limit the response is 429 `{"message": "You're going a bit fast. Try again in N seconds."}` with `Retry-After`. Decorator dependencies run first, so JSON bodies are not read. FastAPI parses an `UploadFile` parameter before *any* dependency, so `uploadPhoto` and `identifyPlant` now get `file` through a `read_upload_file` dependency (in `rate_limit.py`) listed after the limit. They behave the same otherwise. The app only uses `request.client.host`. The Dockerfile CMD adds `--proxy-headers --forwarded-allow-ips "$FORWARDED_ALLOW_IPS"` (default `127.0.0.1`). In `infra/ec2-stack.yaml` the compose default network gets the fixed subnet `172.30.0.0/24`, Caddy gets `172.30.0.10`, and the app trusts only that address. uvicorn's access log then shows the client IP. `openapi.yaml`: a shared `TooManyRequests` response (with the `Retry-After` header) on all 15 limited operations. Frontend `httpService.ts`: on a 429 it shows `toast.error` (id `rate-limit`, so a burst updates one toast), with "Try again in N seconds/minutes" taken from `Retry-After`, and rejects with the same message. The mock service has no HTTP, so it never limits. Note: callers that already `toast.error(e.message)` (the room page's `run`, photo upload, delete dialog) will show the message a second time. Fixing that needs changes outside this issue's files, so I left it as a possible follow-up. `backend/conftest.py`: an autouse `reset_rate_limit` fixture clears `FERNSLOP_RATE_LIMIT` and rebuilds the limiter for every test. The limiter stays on in tests, and the existing suite passes unchanged. Tests: 4 in `app/test_rate_limit.py` (429 + Retry-After + nothing written, even with a bad body; separate buckets and another IP unaffected; IPv6 /64 keying with a client-sent `X-Forwarded-For` ignored; GET/health never limited and the off flag) and 1 in `httpService.test.ts`. Results: backend `uv run pytest` 149 passed, 2 skipped; `uvx ruff check .` clean. Frontend `npm test` 42 passed. e2e `uv run pytest` 2 passed (its own stack, built from the new Dockerfile).
