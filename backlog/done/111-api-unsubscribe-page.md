# [api] Follow-up: unsubscribe page for the digest link
**What:** A frontend route `/unsubscribe?token=...` that calls `POST /api/follows/unsubscribe` and shows the result.
**Why:** The digest in [#013](013-api-weekly-digest.md) links there, and no UI route calls the endpoint yet.
**Edge cases:** An unknown or already used token shows a friendly "already unsubscribed" message, not an error. The token is read from the URL and sent in the body only.

## Comments

- Added the `/unsubscribe?token=...` route (frontend/src/routes/unsubscribe.tsx) calling `GardenService.unfollow` (token from the URL, sent in the POST body only): unsubscribed, "already unsubscribed" for false, and friendly messages for a missing token or network failure; 2 tests in frontend/src/test/unsubscribe.test.tsx, npm test and build pass.
