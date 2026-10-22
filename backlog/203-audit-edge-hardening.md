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
