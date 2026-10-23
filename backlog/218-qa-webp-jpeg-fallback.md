# [qa] Large opaque WebP shrinks in browsers that cannot encode WebP

## Goal

In WebKit/Safari, which cannot encode WebP, a large WebP without transparency is resized and sent as JPEG (quality 0.85) instead of the bigger PNG, so it no longer goes unshrunk and gets a 413 over 5 MB (QA note on [#209](done/209-audit-photo-client-compression.md)). Small.

## Acceptance criteria

- [ ] In WebKit, a 4000x3000 lossy WebP over 5 MB with no alpha is sent as `image/jpeg`, 2048x1536, named `.jpg`, and posts and identifies without a 413.
- [ ] Unchanged: a WebP with alpha (VP8X alpha flag, or VP8L alpha bit) still falls back to PNG with its transparency kept; in Chromium a WebP is still sent as WebP; PNGs never become JPEG; the "not smaller → send original" rule still applies.
- [ ] Tests: the alpha check on an opaque and an alpha WebP header in `src/lib/image.test.ts` (at most 2 tests).

## Out of scope

- An alpha WebP still over 5 MB after the PNG fallback is refused in the browser by [#211](211-audit-photo-reject-in-browser.md).

## Constraints

- `frontend/src/lib/image.ts` (`readWebp` and `encode`), `src/lib/image.test.ts`. Read the alpha flag from the header bytes already read, not by scanning pixels. No new dependency.
- Same file as #211: do not run them in parallel. Check in WebKit with Playwright as #209's QA did.

**Engineer:** `frontend/src/lib/image.ts`: new exported `webpHasAlpha(bytes)` reads transparency from the WebP header bytes already read (the VP8X alpha flag `0x10`, or the VP8L `alpha_is_used` bit after the 14-bit width and height; a plain lossy `VP8 ` has none), with no pixel scan. `resizeImage` picks a fallback type from it: JPEG for an opaque WebP, PNG for anything else. `encode(bitmap, target, type, fallback)` still tries the file's own type first, and only when the browser hands back something else (no WebP encoder) re-encodes as the fallback, at quality 0.85 for JPEG. `renamed` already gives `.jpg`. JPEG and PNG inputs are unchanged: a PNG's fallback is PNG, so it never becomes a JPEG. The "not smaller → send original" check runs after encoding, as before. The doc comment on `resizeImage` now describes this. Note that a lossless opaque WebP (VP8L, alpha bit 0) also becomes a JPEG in WebKit, because it has no transparency to keep. Tests (2), in `src/lib/image.test.ts`: opaque lossy, lossless and extended headers read as no alpha; the VP8X alpha flag and the VP8L alpha bit read as alpha. `npm test`: 56 passed.
Browser check: a static build (`FERNSLOP_STATIC=1 npm run build`) served by a local uvicorn on :59762 with a scratch SQLite DB, `FERNSLOP_RATE_LIMIT=off` and `FERNSLOP_STATIC_DIR`. Playwright drove PostBox (`#post-photo`) and Add plant > Photo (`#plant-photo`) in Chromium and WebKit. The file sent was captured through a `FormData.append` hook, and the stored bytes came from `GET /api/photos/{id}` and were checked with Pillow. 4000x3000 inputs, made with Pillow:
- Opaque lossy WebP (`VP8 `), 12.5 MB. WebKit: sent as `opaque.jpg`, image/jpeg 2048x1536, 2.27 MB. Post 201, identify 200, stored JPEG 2048x1536 RGB. Chromium: sent as image/webp 2048x1536, 1.03 MB, and stored as WebP.
- Opaque lossless WebP (VP8L, alpha bit 0), 15.0 MB. WebKit: sent as `lossless.jpg`, image/jpeg 2048x1536, 437 KB, stored JPEG. Chromium: WebP 2048x1536, 11 KB.
- Lossless WebP with alpha (VP8L alpha bit; left half alpha 0), 7.6 MB. WebKit: sent as `alpha-lossless.png`, image/png 2048x1536, 2.43 MB, stored PNG RGBA, alpha 0 left and 255 right. Chromium: WebP RGBA with alpha kept.
- Lossy WebP with alpha (VP8X alpha flag), 4.1 MB. WebKit: its PNG would be bigger, so it is sent byte for byte unchanged as WebP 4000x3000 (the "not smaller" rule) and stored as WebP RGBA with alpha kept. Chromium: WebP 2048x1536 RGBA with alpha kept.
Every post returned 201 and every identify 200 (no 413). No page errors in either browser. The server was stopped afterwards. Issue left open.
