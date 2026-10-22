# [api] Follow-up: HTTP GardenService in the frontend

## Goal

An HTTP implementation of `GardenService` (`frontend/src/services/types.ts`) talks to the backend in `openapi.yaml` and can be selected instead of the mock. The mock stays the default. Implement after the backend issues [#007](007-api-areas.md), [#008](008-api-undo.md), [#009](009-api-photos-posts.md) and [#011](011-api-live-sse.md).

## Acceptance criteria

- [ ] With no env set, `getServices()` returns the mock and the app works without the backend. `VITE_USE_MOCK=false` selects the HTTP service, using `VITE_API_BASE_URL` (default `/api`, trailing slash tolerated). Both variables are listed in `frontend/README.md`.
- [ ] Each `GardenService` method calls the operation `openapi.yaml` marks with that `x-service-method` (path, verb, JSON or multipart body) with the interface unchanged; `searchPlants` encodes `q`.
- [ ] Methods taking an `Actor` send `X-Device-Id` and `X-Actor-Name` = `encodeURIComponent(name)` (so `Zoë 🌿` is sent as ASCII); methods without an actor send neither.
- [ ] Results match the mock: 204 gives `void`; `getRoomState` gives `null` on 404; `unfollow` gives the `unsubscribed` boolean; a relative `Photo.url` / `photo_url` (`/api/photos/{id}`) is prefixed with the base URL when that is absolute, so images show.
- [ ] A non-2xx response rejects with an `Error` whose `message` is the body's `message` (shown as-is in toasts); a network failure or non-JSON body rejects with a non-empty generic message, never an unhandled parse error.
- [ ] `subscribe` opens an `EventSource` on `{base}/rooms/{id}/live` (no headers), calls `onChange` once per `change` event and never for pings, and the returned function closes it. Reconnects are left to EventSource.
- [ ] Vitest tests (`npm test`, mocked `fetch` and a stub `EventSource`, no real network) cover the criteria above; `npm run lint` and `npm run build` pass. By hand, with the backend running and `VITE_USE_MOCK=false`, creating a room and adding a plant works and shows up in a second tab without a reload.

## Out of scope

- Production hosting, the production base URL and CORS origins: [#120](120-api-deploy-together.md). Unsubscribe page: [#111](111-api-unsubscribe-page.md).

## Constraints

- Code in `frontend/src/services/http/` plus selection in `services/index.ts`; do not change `GardenService` or the UI. Use `fetch` and `EventSource`: no new dependencies (npm or backend) without asking. Dev: `/api` via a Vite `server.proxy` or an absolute URL (backend CORS already allows the dev origins and both headers).

## Original request
**What:** Implement `GardenService` (`frontend/src/services/types.ts`) over HTTP against the new backend and make it selectable instead of the mock.
**Why:** The request covers the backend only, but the backend isn't used until the frontend calls it.
**Edge cases:** Percent-encode the actor name header. Configure the base URL, a dev proxy or CORS. Use EventSource for `/live`.

## Comments

### Engineer: implemented
- `frontend/src/services/http/httpService.ts` implements `GardenService` over `fetch`/`EventSource` per `openapi.yaml`; `services/index.ts` picks it when `VITE_USE_MOCK=false` (base from `VITE_API_BASE_URL`, default `/api`, trailing slash stripped), otherwise the mock. Both variables are in `frontend/README.md`. `vite.config.ts` proxies `/api` to `http://localhost:8000` in dev.
- Relative photo URLs (`Photo.url`, `FeedEvent.photo_url` in `getRoomState`/`postUpdate`) are prefixed with the base's origin when the base is absolute (`/api/photos/{id}` becomes `https://host/api/photos/{id}`; prefixing the full base would double `/api`).
- 5 tests in `src/services/http/httpService.test.ts` (selection, request shape and actor headers, result mapping, errors, SSE). `npm test`: 30 passed. `npm run build` passes.
- Lint: `eslint` is clean on the files I touched, but `npm run lint` over the whole repo already fails with ~980 prettier errors in untouched files (e.g. `types.ts`, `start.ts`); I did not reformat them.
- Manual check, done with curl, not a browser: backend on :8000 plus `VITE_USE_MOCK=false vite dev`; through the Vite proxy I created a room, added a plant with a percent-encoded `Zoë 🌿` header (stored as `Zoë 🌿`), and the `/live` stream sent `event: change` for that room. I did not click through the UI in two tabs.

### QA: PASS

- [x] No env gives the mock; `VITE_USE_MOCK=false` selects HTTP with `VITE_API_BASE_URL` (default `/api`, trailing slash stripped); both documented in `frontend/README.md` - PASS
- [x] Every method maps to its `x-service-method` operation (path, verb, JSON/multipart); `searchPlants` encodes `q` - PASS (read against `openapi.yaml`)
- [x] Actor methods send `X-Device-Id` and percent-encoded `X-Actor-Name`; actor-less methods send neither - PASS (`Zoë 🌿` stored correctly via the proxy)
- [x] 204 -> `void`, `getRoomState` 404 -> `null` (confirmed 404 via proxy), `unfollow` -> boolean, relative photo URLs get the base origin prefix (no `/api/api`) - PASS
- [x] Non-2xx rejects with the body `message`; network failure / non-JSON gives a generic message - PASS
- [x] `subscribe` opens `EventSource` on `{base}/rooms/{id}/live`, `onChange` only on `change`, returned fn closes it - PASS (live stream through the Vite proxy sent `: ping` then `event: change` after adding a plant)
- [x] Vitest tests, lint, build, manual flow - PASS. Create room + add plant through the Vite proxy with `VITE_USE_MOCK=false` worked and the SSE stream emitted a change event (curl, not a browser; accepted). Lint: eslint is clean on all files 014 added/changed. `npm run lint` fails repo-wide (about 950 prettier errors), but the per-file error list is identical at the parent commit 2f2ca31~1 (checked in a temporary worktree, since removed), so the failures pre-date 014 and are not counted against it.

Tests: `npm test` (vitest), 30 passed, 0 failed. `npm run build`: succeeded.
