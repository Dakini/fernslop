# [audit] Add-plant errors are handled like other room actions

## Goal

`pick()` in `routes/r.$roomId.tsx` catches errors from `svc.addPlant` the way `run()` does (#214): a `RateLimitError` shows only the `httpService` toast, and any other error shows one `toast.error` with its message. Nothing reaches the console as an unhandled rejection.

## Acceptance criteria

- [ ] With `FERNSLOP_RATE_LIMIT_<BUCKET>=1` used up, Add plant > pick a plant shows the one rate-limit toast, no `pageerror` in the console, and no "planted" success toast.
- [ ] A 400, 404 or network failure on add plant shows one error toast (the server message, or the usual "Couldn't reach the server..." copy), no success toast and no unhandled rejection.
- [ ] A successful add still shows the "planted" toast and highlights the new plant, as today.

## Out of scope

- Nothing moved out.

## Constraints

- `frontend/src/routes/r.$roomId.tsx` only; reuse `RateLimitError` from `httpService.ts`. Size: small. At most 1 test (none if a browser check covers it).

## Comments

**Engineer:** `pick()` in `frontend/src/routes/r.$roomId.tsx` now wraps `svc.addPlant`, `setFreshId`, the room invalidation and the success toast in the same `try`/`catch` that `run()` uses: a `RateLimitError` is left to the `httpService` toast, and any other error shows one `toast.error(message)`. No other code changed (PostBox untouched), and no test was added because the browser check covers it. `npm test` passes (51 tests).

Browser check (Playwright, Chromium) against the static build served by a local backend on :8347 with scratch SQLite and `FERNSLOP_RATE_LIMIT_WRITE=1/minute`:
- Success (Basil): one toast, "Basil planted — drag it into place". The plant is on the canvas with `animate-bob`, and there are no page errors.
- Real 429 (second add in the same minute): one toast, "You're going a bit fast. Try again in 58 seconds.". There is no "planted" toast, nothing is added, and there is no `pageerror`.
- 404 `{"message":"Plant not found"}` (route interception): one toast, "Plant not found". No success toast and no `pageerror`.
- 400 `{"message":"Bad plant id"}`: one toast, "Bad plant id". No success toast and no `pageerror`.
- Network failure (`route.abort`): one toast, "Couldn't reach the server. Check your connection and try again.". No success toast and no `pageerror`.
The only console errors were the browser's own "Failed to load resource" lines for the failed requests. There were no unhandled rejections.

## QA: PASS

- [x] Rate limit used up: Add plant > pick shows the one rate-limit toast, no `pageerror`, no "planted" toast - PASS
      Backend with `FERNSLOP_RATE_LIMIT_WRITE=1/minute`: added Basil, then picked Mint. Real 429. One new toast, "You're going a bit fast. Try again in 58 seconds.". There was no Mint "planted" toast and Mint was not on the canvas. There was no `pageerror`. The only console error was the browser's "Failed to load resource ... 429" line.
- [x] A 400, 404 or network failure shows one error toast, no success toast and no unhandled rejection - PASS
      Intercepted the add-plant POST with route interception. A 400 `{"message":"Bad plant id"}` showed one toast, "Bad plant id". A 404 `{"message":"Plant not found"}` showed one toast, "Plant not found". `route.abort()` showed one toast, "Couldn't reach the server. Check your connection and try again.". In all three cases there was no "planted" toast, Mint was not on the canvas, and there was no `pageerror`. The only console errors were the browser's "Failed to load resource" lines.
- [x] A successful add still shows the "planted" toast and highlights the new plant - PASS
      Picked Basil. One toast, "Basil planted — drag it into place". Basil was on the canvas with `animate-bob` and there was no page error.

Other room actions were checked as before through `run()`, with no page errors:
- Adding a Bed area: the area appeared.
- Mark watered: "Watered!".
- A 400 on adding a Pond area: one toast, "Bad area".

Tests: `npm test` in `frontend/`, 9 files, 51 passed, 0 failed. Static build `FERNSLOP_STATIC=1 npm run build` succeeded. Browser check: Playwright (Chromium) via `uv run` from `e2e/`, against `uvicorn` on free ports with scratch SQLite. Nothing in the code was changed.
