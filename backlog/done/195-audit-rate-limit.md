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

## QA: PASS

- [x] Default limits per client IP (IPv6 by /64), each overridable by env listed in the docstring - PASS
      Limiter built with defaults create_room 10/h, delete_room 10/h, upload_photo 30/h, identify 20/h, follow 10/h, write 120/min; docstring lists `FERNSLOP_RATE_LIMIT_<BUCKET>`. 11 createRoom calls from one IP: 10x 201 then 429. 11 calls from `2001:db8::1..11` hit 429; `2001:db8:0:1::1` got 201. Env overrides (upload 1/h, identify 1/h, follow 1/h, delete 1/h, write 3/min) each gave 429 on the next call. All 15 write routes carry `rate_limited(...)`; no middleware
- [x] 429 with `Error` body and whole-second `Retry-After`, nothing written, checked before body/store; buckets separate, other IP unaffected - PASS
      429 body `{"message": "You're going a bit fast. Try again in 3600 seconds."}`, `Retry-After: 3600`. Room count unchanged after 429s (incl. an invalid-JSON body). A 20 MB upload over the limit got 429 straight away. With photo at 1/h exhausted, area/follow/identify calls were still served; once the write bucket hit 3/min, postUpdate got 429 (Retry-After 60). Another IP got 201
- [x] `GET`, `/live` and `/api/health` never limited - PASS
      With createRoom limited, GET /api/rooms and /api/health gave 200; 300 health calls all 200. The live route (`routers/live.py`) and health route have no limit dependency
- [x] Tests not broken: autouse reset fixture, `FERNSLOP_RATE_LIMIT=off`, suites pass - PASS
      `reset_rate_limit` autouse fixture in `backend/conftest.py`. With `FERNSLOP_RATE_LIMIT=off` and create_room=1/hour, 5 creates all gave 201. Backend and frontend suites pass (e2e not re-run by QA)
- [x] Frontend 429 friendly toast using `Retry-After`; mock never limits - PASS
      `httpService.ts` turns a 429 into `toast.error("You're going a bit fast. Try again in N seconds/minutes.")` using `Retry-After`; covered by a test in `httpService.test.ts`. The mock service has no 429 path
- [x] Real client IP: `--proxy-headers` + `FORWARDED_ALLOW_IPS`; Caddy fixed address on fixed subnet, only it trusted; untrusted XFF ignored (test); access logs show client IP - PASS
      Ran uvicorn with the Dockerfile CMD flags on free ports, create_room=1/hour, 3 POSTs each with a different spoofed `X-Forwarded-For`. Trusting `172.30.0.10` or nothing: 201, 429, 429, and the access log shows 127.0.0.1. Trusting 127.0.0.1 (the peer acting as proxy): 201, 201, 201, and the log shows 9.9.9.1/2/3. `ec2-stack.yaml`: subnet 172.30.0.0/24, Caddy at 172.30.0.10, app `FORWARDED_ALLOW_IPS: 172.30.0.10`. A test in `test_rate_limit.py` covers the ignored header
- [x] `openapi.yaml` documents 429 with `Retry-After` on every limited operation (shared response) - PASS
      Shared `components/responses/TooManyRequests` with a `Retry-After` integer header is referenced on all 15 limited operations

Tests: `cd backend && uv sync && uv run pytest`, 149 passed, 2 skipped, 0 failed; `cd frontend && npm ci && npm test`, 42 passed, 0 failed
