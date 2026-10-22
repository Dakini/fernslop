# [garden-delete] UI: delete button and confirm dialog on the garden page

## Goal

Anyone with the link can delete a garden from its page, behind a confirm dialog (the only guard, no accounts), using `deleteRoom` from [#150](done/150-garden-delete-api.md) (see `openapi.yaml`). Default decision, unless the user changes it: no owner check.

## Acceptance criteria

- [ ] The garden page header (`routes/r.$roomId.tsx`) has a "Delete garden" button next to Follow and Share, and the index cards have none. At 375px wide the header wraps without sideways scroll and the button is at least 44px high.
- [ ] The button opens `components/ui/alert-dialog.tsx` naming the garden, saying plants, activity, photos and follower emails go for good and it cannot be undone. Cancel has focus first; Cancel, Esc and the overlay close it without deleting. The confirm button is a terracotta "Delete garden". At 375px it fits the screen with stacked buttons.
- [ ] Confirming sends one request (the button is disabled meanwhile), then lands on `/` with a "Garden deleted" toast. The garden is gone from the index (empty state if it was the last) and the deleter never sees the "deleted" page of the next criterion.
- [ ] A failure other than 404 keeps the dialog open with the error as a toast; the garden is unchanged and the button works again. A 404 (someone else deleted it first) counts as success.
- [ ] `GardenService` (`services/types.ts`) gets `deleteRoom(roomId): Promise<boolean>`: true when deleted, false when it was already gone (like `unfollow`), other errors reject. HTTP: `DELETE /rooms/{id}`, no actor headers. Mock: removes the room, its plants, areas, feed and follows, notifies its subscribers, persists, and gives false the second time.
- [ ] A visitor with the garden open elsewhere sees "This garden was deleted" with an "All gardens" link to `/` instead of the blank `if (!state) return null`, with no error toast. Their live subscription is closed (`useRoomLive` in `lib/queries.ts`), so `/live` is not requested again, and no "Reconnecting…" shows.
- [ ] At most 5 new tests: `httpService.test.ts` (path, verb, no actor headers, true/false/reject), `mockService.test.ts` (data gone, subscriber notified, second delete false), a dialog test (names the garden, Cancel focused, pending disabled, error keeps it open), the deleted view. `npm test`, `npm run lint` and `npm run build` in `frontend/` pass.

## Out of scope

- Deleting from the index cards, an undo for a deleted garden and limiting delete to the creator: not planned (a hard delete cannot be undone; there are no accounts).

## Constraints

- Stay in `frontend/src`: `services/` (types, http, mock), `lib/queries.ts`, `routes/r.$roomId.tsx`, and the dialog as its own component in `components/garden/` so it tests without the router. Use `getServices()`, react-query keys `["room", id]` and `["rooms"]`, sonner toasts. Note `AlertDialogAction` closes the dialog on click by default. No new dependencies (AGENTS.md).
- `_docs/design-system.md` is outdated (Django templates): follow the existing shadcn look (`components/ui`, tokens in `styles.css`) and verify with the `design-check` skill at phone, tablet and desktop. `_docs/testing-guidelines.md` is Django-only; use vitest and testing-library as in `src/test` and `components/garden/copyShare.test.tsx`.
