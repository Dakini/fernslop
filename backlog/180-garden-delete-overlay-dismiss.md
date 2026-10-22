# [garden-delete] Clicking outside the delete dialog dismisses it

## Goal

User request: "Clicking outside the dialog dismisses the delete." Clicking the overlay closes the confirm dialog like Cancel and Esc. This reverses [#160](done/160-garden-delete-ui.md) criterion 2, where QA/PM chose to ignore outside clicks.

## Acceptance criteria

- [ ] Clicking the overlay closes the dialog without deleting and without any DELETE request; Cancel stays focused first, and Cancel and Esc still close it.
- [ ] While the delete request is in flight the overlay click, Cancel and Esc are blocked, as now.
- [ ] One dialog test covers the overlay click; checked in a browser against the mock service.

## Constraints

- `frontend/src/components/garden/DeleteGardenDialog.tsx` (and `ui/alert-dialog.tsx` if needed). At most 2 tests.

## Comments

**Engineer:** Clicking the overlay now closes the delete confirm without deleting. Radix hard-codes `onPointerDownOutside` to preventDefault in `AlertDialogContent`, so `ui/alert-dialog.tsx` `AlertDialogContent` gets an optional `overlayProps` passed to its overlay, and `DeleteGardenDialog.tsx` passes `onClick: () => !pending && setOpen(false)` (blocked while the request is in flight, like Cancel and Esc; Cancel is still focused first). One new test in `DeleteGardenDialog.test.tsx` (overlay closes with no delete call; overlay ignored while pending). Browser check (Playwright, Chromium, mock service, 1280 and 375): Cancel focused on open, clicking the overlay closes the dialog and stays on the garden, Esc and Cancel still close, a click inside the dialog keeps it open. The dev server was stopped. Issue left open.
