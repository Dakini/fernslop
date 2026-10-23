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

**QA:**

## QA: PASS

Environment: local uvicorn on a free port (scratch SQLite, `FERNSLOP_RATE_LIMIT=off`) serving `FERNSLOP_STATIC=1 npm run build`; Playwright script in Chromium and WebKit, each case driven through both `#post-photo` and the Add plant `#plant-photo` input (file named `photo.jpg`, `mimeType: image/jpeg`), counting `POST /api/photos` / `POST /api/plants/identify`, toasts and console errors. What was actually sent was read by wrapping `fetch` (FormData file type/size/decoded dimensions).

- [x] Wrong first bytes refused with toast, no request, in both inputs - PASS
      Random bytes, a text file and HEIC bytes, all named `.jpg`: toast `Please use a JPG, PNG or WebP image`, 0 requests, no preview, in both inputs and both browsers. A real PNG named `.jpg` is accepted and sent as `image/png` (Chromium and WebKit, both inputs; 201 / 200).
- [x] Over 5 MB after resizing: toast, no request - PASS
      A 7.3 MB animated WebP (not resized): toast `That photo is over 5 MB`, 0 requests, both inputs and both browsers.
- [x] No console error in Chromium for either case - PASS
      0 console errors (and no 413/415) for all the refused cases above, in Chromium and WebKit.
- [x] Identify failures are a toast; low-confidence note inline - PASS
      Add plant: refused files toast (above); a mocked 500 from identify shows the toast `Something went wrong. Please try again.`; an identify returning `[]` shows the inline `We couldn't be sure — try searching instead` and no toast. A mocked 429 on either input shows only the single rate-limit toast (`You're going a bit fast. Try again in 30 seconds.`).
- [x] Mock uses the same helper; server unchanged - PASS
      `mockService` imports `checkImage` from `lib/image.ts` (its own copy removed); the messages are defined once in `lib/image.ts`. `git diff abc4bb7 -- backend` is empty. (Pre-existing: `httpService.ts` still has its own `PHOTO_TOO_LARGE` string for the server's 413; outside this issue.)
- [x] Tests - PASS
      `image.test.ts` refuses HEIC bytes named `.jpg` and accepts/retypes a real PNG; `e2e/test_post_photo.py::test_heic_renamed_jpg_is_refused_in_the_browser_without_a_request` passes.

#209 resize still works: a 7.1 MB (Chromium) / 9.7 MB (WebKit) 12 MP JPEG is sent as a 2048x1536 JPEG (0.75 MB / 1.8 MB) from both inputs, 201/200, no toast. A small valid JPEG sends 1 request, no toast.

Known gap (not a criterion): a truncated JPEG whose header is intact reaches the server and gets a 415 with a console error in the post input (the identify endpoint accepts it, 200). This happens below 512 KB too (a 55 KB half-JPEG), not only above it as the engineer's comment says. Its first bytes are a valid JPEG and it is not oversized, so it is outside both refusal criteria; the user still sees the right toast. Worth a backlog note if it matters.

Tests: `cd frontend && npm test` 54 passed, 0 failed; `cd e2e && E2E_BASE_URL=... uv run pytest` 5 passed, 0 failed.
