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
