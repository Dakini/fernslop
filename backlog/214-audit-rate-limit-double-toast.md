# [audit] A 429 shows its message once

## Goal

On a 429 the user sees exactly one message: the `rate-limit` toast that #195 shows in `httpService.ts`. Today the room page's `run()`, the post photo upload and the delete-garden dialog toast `e.message` again, and the create-garden dialog, follow form and identify note repeat it inline.

## Acceptance criteria

- [ ] With the backend limit set to 1 (`FERNSLOP_RATE_LIMIT_<BUCKET>`), a second room action (move, care, area, post, undo), photo upload, garden delete, garden create, follow and identify each show the one rate-limit toast and no second toast or inline copy; dialogs stay usable.
- [ ] Any other error (400, 404, 413, 507, network) still shows once, where it does today.
- [ ] A `Retry-After` of an hour or more reads `Try again in N hours` (for the daily caps of #207 and #210); under an hour reads as today.

## Out of scope

- Identify errors moving from the inline note to a toast: [#211](211-audit-photo-reject-in-browser.md).

## Constraints

- `frontend/src/services/http/httpService.ts` (+ test), `routes/r.$roomId.tsx`, `components/garden/DeleteGardenDialog.tsx`, `CreateRoomDialog.tsx`, `AddPlantDialog.tsx`. One way to tell a rate-limit rejection apart (e.g. an exported `RateLimitError`), used by every caller; the mock never limits. At most 2 tests.

## Comments

**Engineer:** `httpService.ts` now exports `RateLimitError` and rejects every 429 with it, after showing the one `rate-limit` toast as before. Every caller checks `instanceof RateLimitError` and then shows nothing of its own: the room page `run()` (move, care, area, post, undo, remove), the post photo upload and the follow form in `routes/r.$roomId.tsx`, `DeleteGardenDialog` (it still resets pending, so the dialog stays usable), `CreateRoomDialog` (no inline error) and `AddPlantDialog` identify (no notice). The follow form also clears its old inline error on resubmit. Every other error goes through the same path as before. `tooFastMessage` reads 3600 s or more as `N hour(s)` (rounded up). Under an hour it reads as it did before, so 3599 s is "60 minutes". The mock is unchanged. Tests: I extended the existing 429 test to assert `RateLimitError` and exactly one `toast.error` call, and added one test for the hours wording. `npm test`: 50 passed. I also ran a browser check with Playwright against a local backend on :8091, using a scratch SQLite DB and every `FERNSLOP_RATE_LIMIT_<BUCKET>=1/day`, with Vite on :5191. I used up each bucket once, then triggered create garden, Bed (area), post photo, follow, identify and delete garden in the UI. Each showed exactly one toast, "You're going a bit fast. Try again in 24 hours.", and the text appeared once on the page. The create and delete dialogs stayed open and enabled. A 1/hour run showed "Try again in 60 minutes". Not covered: `pick()` (add plant) has no catch today, so a 429 there shows only the toast plus an unhandled rejection in the console. That is outside this issue's file scope for changes beyond the listed callers. Issue left open.
