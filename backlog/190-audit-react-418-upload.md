# [audit] Verify the React #418 fix and that photo upload works end to end

## Goal

Verify commit `b32a780` (made outside the process): direct loads of `/` and `/r/<id>` hydrate without React #418, the Add-plant photo input takes the same file twice, and post-photo upload and photo identify work end to end on the docker stack on desktop and a phone-sized screen. The code is believed done; the engineer only fills gaps (the e2e test below) and files any real bug found as its own issue.

## Acceptance criteria

- [ ] `frontend/src/router.tsx` sets one `defaultPendingComponent` (`PagePending`) and no route sets its own `pendingComponent`.
- [ ] On the production build (`make up`, Chromium at 1280×800 and 390×844), loading `/` and `/r/<seed room id>` directly logs no React #418 or other hydration error, and the page renders.
- [ ] Add plant > Photo: choosing the same file twice in a row sends two `POST /api/plants/identify` and shows candidates both times (the stub provider is fine).
- [ ] Posting text plus a JPEG, PNG or WebP under 5 MB shows the preview, adds the post, the image loads from `/api/photos/{id}`, and a second browser on the room sees it without reloading.
- [ ] For both the post photo and identify: a file over 5 MB shows the toast `That photo is over 5 MB`; a GIF or HEIC file (also one renamed to `.jpg`) shows `Please use a JPG, PNG or WebP image`; neither leaves a spinner or a console error.
- [ ] One new e2e test in `e2e/` posts a photo and a second browser context sees it in the feed.

## Out of scope

- Unknown paths such as `/nope` still logging #418: [#191](191-audit-404-hydration.md).
- Compressing photos in the browser so large phone photos fit under 5 MB (`_docs/lovable-spec.md`, "compressed client-side first"): [#209](209-audit-photo-client-compression.md).
- Any real upload bug found while checking: file a new issue and link it in a comment here.

## Constraints

- Code changes only in `e2e/` (see `e2e/README.md`); if another criterion fails, comment on the issue rather than widen it.
- At most 1 new test; follow `_docs/testing-guidelines.md`.

## Comments

**Engineer:** Verified on a throwaway compose stack (`fernslop-e2e`, port 8123; the stack on :8000 was not touched) with a Playwright script in Chromium at 1280×800 and 390×844.

- Criterion 1: pass. `router.tsx` sets `defaultPendingComponent: PagePending`; no route sets `pendingComponent`.
- Criterion 2: pass. Direct loads of `/` and `/r/<Elm Street Allotment id>` render their heading with no #418, hydration error or any other console error at both sizes.
- Criterion 3: pass. Same JPEG chosen twice: two `POST /api/plants/identify`, candidates shown both times, at both sizes.
- Criterion 4: pass. JPEG, PNG and WebP posts each show the preview, add the post, the image loads (`naturalWidth > 0`) from `/api/photos/{id}`, and a second context sees it without reloading, at both sizes.
- Criterion 5: partly. The messages are right everywhere: over 5 MB gives `That photo is over 5 MB`; GIF, HEIC, HEIC renamed to `.jpg` and GIF renamed to `.jpg` give `Please use a JPG, PNG or WebP image`; no spinner or "Uploading…" is left behind. Two gaps against the wording: (a) for identify the message is the inline status note at the top of the Add plant dialog, not a toast (the post photo does use a toast); (b) the checks are server-only, so Chromium logs `Failed to load resource: ... 413 (Content Too Large)` / `415 (Unsupported Media Type)` as a console error for each rejected file. The app itself logs nothing. Neither is a broken upload, so filed as [#211](211-audit-photo-reject-in-browser.md) rather than fixed here (code changes are limited to `e2e/`).
- Criterion 6: added `e2e/test_post_photo.py` (one test, listed in `e2e/README.md`): a gardener posts text plus a JPEG and a second browser context sees the photo load in its feed live.

Tests: `make test-e2e` 2 passed (own throwaway stack, removed afterwards); `cd backend && uv run pytest` 134 passed, 2 skipped.
