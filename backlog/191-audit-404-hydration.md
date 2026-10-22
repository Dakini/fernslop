# [audit] Unknown URLs still log React #418 on load

## Goal

Loading an unknown path directly from the production build shows the friendly 404 page with no hydration error in the console. Remaining edge of the #418 fix verified in [#190](190-audit-react-418-upload.md): the static build prerenders one shell at `/`, and the root not-found component renders different markup.

## Acceptance criteria

- [ ] On the production build (`make up`, Chromium), loading `/nope` and `/a/b/c` directly logs no React #418 or other hydration error and shows the "Page not found" page; its "Go home" link works.
- [ ] `/r/<random UUID>` and `/r/not-a-uuid` loaded directly show the room's own not-found page (`notFoundComponent` in `r.$roomId.tsx`) with no hydration error.
- [ ] `/unsubscribe` and `/unsubscribe?token=x` loaded directly hydrate cleanly and show their existing result screens.
- [ ] No regression: `/` and `/r/<seed room id>` still hydrate cleanly, and following an unknown link inside the app still shows the 404 page.
- [ ] One e2e test loads `/nope` and checks for the 404 heading and no console error.

## Out of scope

- Nothing moved out of this issue.

## Constraints

- `frontend/src/routes/__root.tsx`, `frontend/src/router.tsx`, `e2e/`. Keep `PagePending` as the single prerendered shell; the 404 page keeps its look.
- Check against the production build served by the backend (`FERNSLOP_STATIC=1`, see `Dockerfile`), not `npm run dev`.
- After #190 (reuse its e2e helpers). At most 1 new test.

## Comments

**Engineer:** Fixed in `edceb5f`, changing only `frontend/src/routes/__root.tsx` and `e2e/`.

Cause: every path gets the one prerendered shell, which is `/` with `PagePending` inside two Suspense boundaries (the root Outlet's and the index match's). On an unknown path the root match is a global not-found, so on the client the root Outlet renders the not-found component straight away and skips both boundaries. The markup differed, so React threw #418. Fix: the root `NotFoundComponent` wraps the unchanged 404 page (now `NotFoundPage`) in TanStack's `ClientOnly`. Its fallback is the shell's exact markup (`<Suspense><Suspense><PagePending/></Suspense></Suspense>`). During hydration it matches the shell, and once hydration is done the 404 swaps in. After hydration `ClientOnly` renders its children at once, so in-app navigation shows the 404 with no flash. `PagePending` is still the only prerendered shell, and the 404 looks the same as before.

Checked on the production static build: first `FERNSLOP_STATIC=1 npm run build` served by the backend on :8191, then my own compose stack (`fernslop-e2e191`, port 8291, removed afterwards; :8000 not touched). Chromium:
- `/nope` and `/a/b/c`: before the fix each threw `Minified React error #418`. After it, "Page not found" shows with no console or page errors. "Go home" goes to `/` without a reload. Browser Back then shows the 404 again inside the app (same document), with no errors, at 1280×800 and 390×844.
- `/r/<random UUID>` and `/r/not-a-uuid`: "This garden can't be found" shows with no hydration error. Chromium does log `Failed to load resource: ... 404` for the room API request. That is the browser's network log for the API's 404, not an app or hydration error, and it was there before this change.
- `/unsubscribe` shows "This link looks incomplete" and `/unsubscribe?token=x` shows "Already unsubscribed". Both have no errors.
- `/` and `/r/<Elm Street Allotment id>` still hydrate with no errors.

Test: `e2e/test_not_found.py` (one test, listed in `e2e/README.md`). It loads `/nope`, checks the heading and the "Go home" link, and asserts no console or page error. It did not use the #190 helpers (`create_garden`, `image_has_loaded`), because it creates no garden and loads no image. It only uses the shared `new_gardener` fixture.

Tests: e2e 3 passed (run against my own `fernslop-e2e191` compose stack via `E2E_BASE_URL`, so it would not clash with other agents using the fixed `fernslop-e2e` project); `cd frontend && npm test` 41 passed. `tsc` and `eslint` report no new problems in `__root.tsx`. Both still report existing errors in other files and existing prettier issues, the same as on `main`.
