# [audit] Reject wrong-type and oversized photos in the browser, and show identify errors as a toast

## Goal

A photo the server would refuse is caught in the browser before anything is sent, so a phone does not upload a whole file to learn it is too big and Chromium logs no `413`/`415` console error, and identify errors appear as a toast like the post photo's (found while verifying #190).

## Acceptance criteria

- [ ] In both the post photo and the Add plant photo input, a file whose first bytes are not JPEG, PNG or WebP (a HEIC renamed `.jpg`, a GIF, a text file) shows the toast `Please use a JPG, PNG or WebP image` and sends no request, whatever its name or `file.type`.
- [ ] A file still over 5 MB after #209's resizing shows the toast `That photo is over 5 MB` and sends no request.
- [ ] Neither case logs a console error in Chromium.
- [ ] Identify failures (these checks and server errors) show as a toast; the low-confidence `We couldn't be sure — try searching instead` note stays inline in the dialog.
- [ ] The mock service checks through the same helper, so the messages live in one place; the server's checks are unchanged.
- [ ] Tests: the helper refuses HEIC bytes named `.jpg` and accepts a real PNG; one e2e that a renamed HEIC shows the toast with no request.

## Out of scope

- None.

## Constraints

- `frontend/src/lib/image.ts` (extend #209's `prepareImage`), `routes/r.$roomId.tsx` (`PostBox`), `components/garden/AddPlantDialog.tsx`, `services/mock/mockService.ts`, `e2e/`. Magic bytes as in `backend/app/uploads.py` `sniff_image_type`.
- After #209 and #214 (same files). At most 3 tests.
