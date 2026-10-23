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
