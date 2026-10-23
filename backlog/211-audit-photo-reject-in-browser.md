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

## Comments

**Engineer:** Implemented.

- `lib/image.ts`: new `sniffImageType` (same magic bytes as the server's `sniff_image_type`) and `checkImage(file)`, which throws the server's messages (`UNSUPPORTED_TYPE_MESSAGE`, `TOO_LARGE_MESSAGE`, now defined once here) and returns the file typed by its bytes, so a real PNG named `.jpg` is sent as `image/png` and the server does not 415 it. A file of 512 KB or less whose JPEG/PNG/WebP header cannot be parsed (`readImageInfo` returns null) is refused as the wrong type too. `prepareImage` now sniffs the type first, resizes (#209's code, now the private `resizeImage`, using the sniffed type), then runs `checkImage`, so the size check applies after resizing. Reading bytes falls back to `FileReader` where `Blob.arrayBuffer` is missing (jsdom, old Safari).
- `PostBox` needed no change: `prepareImage` was already inside its `try`, which toasts non-rate-limit errors. `pick()` untouched.
- `AddPlantDialog`: identify errors (the browser checks and server errors) are now `toast.error`; `RateLimitError` is still skipped, so it shows only its own toast. The low-confidence note stays inline.
- `mockService`: `identifyPlant`/`uploadPhoto` use `checkImage` (its own type/size copy removed); its tests now use real PNG header bytes. Server unchanged.
- Tests: `image.test.ts` (HEIC bytes named `.jpg` refused, real PNG named `.jpg` accepted and retyped), `e2e/test_post_photo.py` (renamed HEIC: toast, no `POST /api/photos`, no console error).

Checked: `npm test` 54 passed; e2e 5 passed against a local uvicorn + static build via `E2E_BASE_URL`. A Playwright script in Chromium and WebKit sent random bytes `.jpg`, a JPEG start with a garbage header, a text file `.jpg`, a 7 MB animated WebP, a 6-7 MB 12 MP JPEG and a small JPEG through both the post photo and the Add plant input. The rejected ones showed the right toast with 0 requests; the two good photos sent 1 request each with no toast; no console errors and no 413/415 anywhere.

Residual: a file over 512 KB with a valid magic and a broken body (e.g. truncated mid-scan) still reaches the server and gets its 415. Decoding every file in the browser to catch this would be inconsistent anyway (browsers draw truncated JPEGs that Pillow refuses), so I left it.
