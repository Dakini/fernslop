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
