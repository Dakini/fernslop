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
