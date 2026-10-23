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
