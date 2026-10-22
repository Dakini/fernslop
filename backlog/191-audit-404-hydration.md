# [audit] Unknown URLs still log React #418 on load
**What:** Loading an unknown path such as `/nope` must not log a hydration error: the root not-found component should render in a way that matches the prerendered SPA shell (or render client-only), and still show the friendly 404.
**Why:** Remaining edge from the #418 fix in #190 (`b32a780`): the static build prerenders one shell at `/`, and the root 404 component differs from it, so hydration fails with #418 (HTML).
**Edge cases:** Old room links to a deleted garden (`/r/<unknown id>`) and the `/unsubscribe` page loaded directly must also hydrate cleanly; check with the production build served by the backend, not the dev server.
