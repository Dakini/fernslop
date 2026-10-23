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
