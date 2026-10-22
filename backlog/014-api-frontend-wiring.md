# [api] Follow-up: HTTP GardenService in the frontend
**What:** Implement `GardenService` (`frontend/src/services/types.ts`) over HTTP against the new backend and make it selectable instead of the mock.
**Why:** The request covers the backend only, but the backend isn't used until the frontend calls it.
**Edge cases:** Percent-encode the actor name header. Configure the base URL, a dev proxy or CORS. Use EventSource for `/live`.
