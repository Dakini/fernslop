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
