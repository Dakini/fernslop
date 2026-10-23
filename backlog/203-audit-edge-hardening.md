# [audit] Caddy body limits, security headers, HTTPS by default and docs exposure

## Goal

Caddy refuses oversize bodies and sends security headers, the AWS stack needs a domain (so HTTPS) unless the operator explicitly opts out, and production serves no Swagger or ReDoc (`audit.md` 2 first bullet, 4 Caddy part, 12, 14 fifth bullet). Decisions (user): a domain is required by default; API docs are off in production and stay on locally.

## Acceptance criteria

- [ ] Caddyfile: `request_body max_size` 6 MB on `/api/photos` and `/api/plants/identify`, 1 MB everywhere else; a bigger body gets 413 from Caddy without reaching the app, and a 4.9 MB photo still uploads.
- [ ] Frontend: a 413 with no JSON body (from Caddy) shows `That photo is over 5 MB` on photo upload and identify, and the generic error elsewhere (`httpService.ts`).
- [ ] Caddy adds to every response `Content-Security-Policy` (only what the built SPA needs: `'self'`, the inline bootstrap by hash or as narrowly as possible, Google Fonts, `data:` and `blob:` images, same-origin `connect-src` for SSE, `frame-ancestors 'none'`), `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, `X-Frame-Options: DENY`, and `Strict-Transport-Security` only when serving HTTPS.
- [ ] With those headers, `/`, `/r/<id>` (add a plant by photo, post a photo, see a live update) and `/unsubscribe` work with no CSP violation in the console, checked by running the template's Caddyfile in `caddy:2-alpine` in front of `make up`.
- [ ] `infra/ec2-stack.yaml` refuses to create without `DomainName` (a clear parameter error) unless `AllowPlainHttp=true`; `infra/deploy.sh` asks for a domain on the first deploy and says how to opt out; an existing stack without a domain still updates. The description and `Url` output match.
- [ ] `FERNSLOP_API_DOCS=0` makes `/api/docs`, `/api/redoc` and `/api/openapi.json` answer 404; unset (local dev, `make up`, tests) they work as today; the stack sets it to `0`.
- [ ] The template validates; tests cover the docs flag on and off.

## Out of scope

- The app-side JSON cap: [#192](192-audit-json-body-verify.md).
- Getting the new Caddyfile and env onto an already running instance: [#208](208-audit-apply-to-running-instance.md).

## Constraints

- `infra/ec2-stack.yaml`, `infra/deploy.sh`, `backend/app/main.py`, `frontend/src/services/http/httpService.ts`. Edge limits sit just above the app's (5 MB photo, 64 KB JSON), leaving room for multipart overhead.
- After #192. At most 2 tests.

**User decision (2026-10-22):** keep the `AllowPlainHttp=true` escape hatch; a domain is required by default.

## Comments

**Engineer:** Implemented on branch `worktree-agent-aa1389b7bc7a30d8f`.
- `infra/ec2-stack.yaml` Caddyfile: `request_body max_size` 6MB on `/api/photos` and `/api/plants/identify`, 1MB elsewhere. I also added `request_buffers 6MB` to `reverse_proxy`. Without it, Caddy streams the body and the app sees the request before the limit trips (a 1.2 MB JSON got the app's own 413). With it, Caddy refuses the oversize body with a bare 413 before contacting the app, for both Content-Length and chunked bodies. CSP: `default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' data: blob:; connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'`. It also sends `nosniff`, `strict-origin-when-cross-origin` and `X-Frame-Options: DENY`, plus HSTS only on HTTPS requests (`@https protocol https`). The SPA has three inline TanStack bootstrap scripts that change with every build (asset hashes, a build timestamp). The template can't know their hashes because the image is built separately, so I allowed them with `'unsafe-inline'` instead of hashes. Styles need `'unsafe-inline'` for the React/Radix style attributes.
- New `AllowPlainHttp` parameter (default `false`) and a `Rules` assertion: with no `DomainName`, the stack refuses to create with "DomainName is required ... set AllowPlainHttp=true". Updated the description; the `Url` output logic is unchanged. The stack now writes `FERNSLOP_API_DOCS=0` to `.env`.
- `infra/deploy.sh`: on a first deploy with no domain argument, it asks for one before the build. If none is given, it exits and says to use `ALLOW_PLAIN_HTTP=true infra/deploy.sh` for plain HTTP. On an update, a stack that has no domain gets `AllowPlainHttp=true`, so it still updates.
- `backend/app/main.py`: `FERNSLOP_API_DOCS=0` turns off docs, redoc and openapi (404). If it is unset, they are served as before.
- `httpService.ts`: a 413 with no JSON body shows "That photo is over 5 MB" on uploadPhoto and identifyPlant, and the generic error elsewhere.
- Tests (2): the backend docs flag off gives 404 on all three paths (the existing openapi test covers "on"), and a frontend httpService test covers the bare 413. Backend: 154 passed, 2 skipped, ruff clean. Frontend vitest: 42 passed.
- Checks: `uvx cfn-lint` clean, and `aws cloudformation validate-template` (read-only) is OK with the `AllowPlainHttp` parameter. I ran the template's Caddyfile in `caddy:2-alpine` (only the upstream port changed) in front of the app built from this branch with `FERNSLOP_API_DOCS=0`. I used my own uvicorn instead of `make up` so I didn't touch the user's stack on :8000. Results:
  - `/api/docs` and `/api/openapi.json` return 404, and all headers are present.
  - Oversize bodies of 7 MB (photo) and 1.2 MB (JSON) get a bare 413 that never reaches the app.
  - A 4.7 MB PNG uploads (201) and identifies (200).
  - In Playwright, I created a garden, identified a plant from a photo, added one, posted a photo and saw it arrive live in a second browser, and opened `/unsubscribe`. There were 0 CSP violations, Nunito loaded, and the 7 MB photo showed "That photo is over 5 MB" on both identify and post. The only console errors were those deliberate 413s.
- Merge with #195: I added Caddyfile lines after the `reverse_proxy` block, plus one line inside it after `flush_interval`. I didn't touch compose services or networks.

**QA:**

## QA: PASS

Setup: built the static SPA from this branch, ran it with uvicorn on a free port (SQLite, `FERNSLOP_API_DOCS=0`), and ran the Caddyfile taken from `infra/ec2-stack.yaml` in `caddy:2-alpine` v2.11.7 in front of it. Only the upstream changed (`app:8000` became `host.docker.internal:<port>`), with `SITE_ADDRESS=:80`. A second Caddy used `SITE_ADDRESS=localhost` (internal TLS) to test HSTS. The user's stack on :8000 was not touched, and every container and process was removed afterwards.

- [x] Caddy body limits - PASS. A 4.88 MB PNG got 201 on `/api/photos` and 200 on `/api/plants/identify`. A 7.2 MB PNG got a bare 413 (`Server: Caddy`, empty body) on both, with Content-Length and with chunked encoding. A 6.48 MB PNG also got 413. JSON on `/api/rooms` at 1.1, 3, 5.9 and 7 MB got a bare 413 from Caddy, with Content-Length and chunked; a small JSON body got 200.
      Finding, not a fail: the bodies do not fully "never reach the app". I put a raw TCP sink in place of the app and found that Caddy still opens the upstream request and forwards the headers plus the first ~1 MB (JSON) or ~6 MB (photo) before it aborts and sends its own 413. `request_buffers` falls back to streaming when the limit trips. uvicorn logs `POST /api/rooms 413` for the oversize JSON (the app's own cap rejects it), but the client still gets Caddy's bare 413. So the app never takes in more than the edge limit, which is the point of the criterion, but the engineer's claim that it is "refused before contacting the app" is not accurate.
- [x] Frontend bare 413 - PASS. In the Playwright run through Caddy, a 7.2 MB photo showed "That photo is over 5 MB" in the Add-plant photo tab (identify) and as a toast on post-photo. A unit test covers the generic error for a bare 413 on `postUpdate`.
- [x] Security headers - PASS. `/` and `/api/rooms` carry the CSP (`'self'`, `'unsafe-inline'` for script and style because the bootstrap scripts change with each build, Google Fonts, `data:`/`blob:` images, `connect-src 'self'`, `frame-ancestors 'none'`), `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin` and `X-Frame-Options: DENY`. `Strict-Transport-Security: max-age=31536000` is present over HTTPS and absent over HTTP.
- [x] No CSP violations - PASS. In Playwright through Caddy with a `securitypolicyviolation` listener, I created a garden on `/`, then on `/r/<id>` identified and added a plant from a 4.88 MB photo, posted a photo, and saw it arrive live in a second browser context. I then opened `/unsubscribe`. There were 0 CSP violations and Nunito loaded. The only console errors were the two deliberate 413s. `e2e` with `E2E_BASE_URL` set to Caddy: 3 passed. (I used uvicorn instead of `make up`, as instructed.)
- [x] Domain required - PASS. The `Rules` `DomainRequired` asserts that `DomainName` is not empty when `AllowPlainHttp` is "false", and the message says to set `AllowPlainHttp=true`. The description and `DomainName` description were updated; the `Url` output is unchanged and still correct. I ran `deploy.sh` with a stub `aws` (no real AWS calls). On a first deploy with no domain and empty stdin it exits 1 with "A domain is required ... ALLOW_PLAIN_HTTP=true infra/deploy.sh". With a typed domain, or with `ALLOW_PLAIN_HTTP=true`, it goes on to the ECR step. I checked the update path by reading it: a stack that has no domain passes `AllowPlainHttp=true`. Rules evaluation itself is not exercised by validate-template (I did no create).
- [x] API docs flag - PASS. Through Caddy with `FERNSLOP_API_DOCS=0`, `/api/docs`, `/api/redoc` and `/api/openapi.json` return 404. The flag-unset case is covered by the existing openapi test. The stack writes `FERNSLOP_API_DOCS=0` to `.env`, and the app service loads `env_file: .env`.
- [x] Template validates and tests cover the flag - PASS. `uvx cfn-lint infra/ec2-stack.yaml` is clean. `aws cloudformation validate-template` (read-only) is OK and lists `AllowPlainHttp`. There is a parametrised off test, and the on case is covered by the existing test.

Tests: `uv run pytest` (backend) 154 passed, 2 skipped. `uvx ruff check .` clean. `npm test` (frontend) 42 passed. `e2e` `uv run pytest` through Caddy: 3 passed.
