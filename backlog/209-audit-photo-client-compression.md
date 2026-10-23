# [audit] Compress large photos in the browser before upload

## Goal

A phone photo over 5 MB posts and identifies instead of failing with 413, because the browser downscales it first, as `_docs/lovable-spec.md` asks ("compressed client-side first"). Moved out of #190.

## Acceptance criteria

- [ ] A still JPEG, PNG or WebP over 1 MB whose longest side is over 2048 px is resized to 2048 px on its longest side before `uploadPhoto` and `identifyPlant`; a 12 MP JPEG of about 6 MB posts and identifies without a 413.
- [ ] A JPEG stays a JPEG (quality about 0.85). A PNG or WebP keeps its transparency and is never turned into a JPEG (same type if the browser can encode it, else PNG).
- [ ] Sent byte for byte unchanged: files of 1 MB or less, images already 2048 px or smaller, animated PNG or WebP (`acTL` / `ANIM` chunk), and any file whose resized version is not smaller.
- [ ] A JPEG with EXIF Orientation 6 is stored upright, checked in Chromium and WebKit (Playwright).
- [ ] If the browser cannot decode or resize the file (unsupported, out of memory), the original is sent and the server's answer shows as today.
- [ ] The mock service gets the resized file too; the server's 5 MB limit and messages are unchanged.
- [ ] Tests: the keep-or-resize decision (size, dimensions, animation); one e2e post of a large JPEG.

## Out of scope

- Rejecting wrong-type and still-oversized files in the browser: [#211](211-audit-photo-reject-in-browser.md).

## Constraints

- New `frontend/src/lib/image.ts` (one `prepareImage(file): Promise<File>`), called from `PostBox` in `routes/r.$roomId.tsx` and from `components/garden/AddPlantDialog.tsx`; `e2e/`. Browser APIs only (`createImageBitmap`, canvas or `OffscreenCanvas`), no new dependency. Decode at reduced size where supported to spare low-end phones; show the existing uploading state while it works.
- At most 3 tests.

**Engineer:** New `frontend/src/lib/image.ts` exports `prepareImage(file): Promise<File>`, plus the pure `readImageInfo` and `resizeTarget` it uses, which #211 can reuse. It reads the first 512 KB of the file to get the dimensions, the JPEG EXIF orientation (5-8 swap width and height) and the APNG `acTL` / WebP `ANIM` or VP8X animation flag. A still JPEG, PNG or WebP over 1 MB whose longest side is over 2048 px is decoded with `createImageBitmap(file, {imageOrientation: "from-image", resizeWidth, resizeHeight, resizeQuality: "high"})`, so the browser decodes straight to the target size where it supports that. If those options throw, it falls back to a full decode. The image is then drawn on a canvas and encoded: JPEG at 0.85, PNG as PNG, and WebP as WebP if `toBlob` really returns WebP, otherwise PNG (the name then ends in `.png`). The original is sent unchanged when the file is 1 MB or less, 2048 px or smaller, animated, or has a header it cannot read. It is also sent unchanged when decoding or encoding fails (any exception) or the result is not smaller. `PostBox` in `routes/r.$roomId.tsx` (only the upload line and the import changed) and `AddPlantDialog` call it inside their existing try, after the "Uploading…" or "Looking closely…" state is set. The mock gets the prepared file because the callers prepare it before calling the service. Server limits and messages are unchanged. Tests (3): `src/lib/image.test.ts` checks the keep-or-resize decision (size and dimensions) and that animated PNG and WebP headers are never resized. `e2e/test_post_photo.py::test_large_phone_photo_is_shrunk_in_the_browser_and_posts` draws a 4000x3000 JPEG over 5 MB in the page, posts it and asserts the posted image is 2048x1536. `npm test`: 52 passed. e2e (`E2E_BASE_URL` pointing at a local backend): 4 passed.
Browser check: a static build (`FERNSLOP_STATIC=1`) served by a local uvicorn on :53595, with a scratch SQLite DB and `FERNSLOP_RATE_LIMIT=off`. I drove it with Playwright in Chromium and WebKit, captured the files sent from `fetch`, and checked the stored bytes with Pillow:
- 4000x3000 JPEG, 7.5 MB: sent as image/jpeg, 749 KB in Chromium and 1.84 MB in WebKit. Stored at 2048x1536. The post shows and its image loads. Identify returned 200 with candidates in both browsers.
- 4000x3000 JPEG with EXIF Orientation 6 and a red band on the stored left edge, 6.8 MB: stored at 1536x2048 with the red band on top and no EXIF orientation, in both browsers (upright).
- 4000x3000 transparent PNG (left half alpha 0), 7.3 MB: sent as image/png, 1.8 MB in Chromium and 1.9 MB in WebKit. Stored at 2048x1536 RGBA, with alpha 0 on the left and 255 on the right.
- 3000x2500 transparent PNG, 3.5 MB, whose resized version comes out bigger: sent byte for byte unchanged.
- 2500x2200 animated PNG (2.0 MB) and 800x600 JPEG (52 KB): sent unchanged. The APNG is stored still animated.
- An undecodable 2 MB "PNG" (valid IHDR, random body): the original is sent, and the server's 415 "Please use a JPG, PNG or WebP image" shows as a toast in both browsers.
No page errors. Not checked: a WebP input. It takes the same code path as PNG, but WebKit's fallback from WebP to PNG encoding was not exercised. I installed Playwright's WebKit browser once (`uv run playwright install webkit`), with no dependency change. Issue left open.
