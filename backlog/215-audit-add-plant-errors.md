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
