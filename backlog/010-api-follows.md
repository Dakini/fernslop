# [api] Follow and unsubscribe

## Goal

`POST /api/rooms/{roomId}/follows` and `POST /api/follows/unsubscribe` behave as `openapi.yaml` defines (`followRoom`, `unfollow`), using the follow methods of `StoreProtocol` from [#002](002-api-seed-store.md).

## Acceptance criteria

- [ ] A first follow with `{"email": "  Ada@Example.COM "}` on a seeded room returns 201 and a `RoomFollow` (UUID4 `id`, `room_id`, email `ada@example.com`, `created_at` from `app.timestamps.now()`). No actor headers are needed.
- [ ] The body has exactly the four `RoomFollow` keys and never the unsubscribe token; a test checks the 201 and 200 bodies for the stored token string. The stored token is `secrets.token_urlsafe(32)`.
- [ ] Following again with the same email in any case returns 200 with the same `id` and `created_at`, and the store still holds one follow. The same email on a different room is a separate 201.
- [ ] An email that is missing, not a string, over 254 characters or not `local@domain.tld` (one `@`, no spaces, a dot in the domain) gives 400 `That email doesn't look right`; no follow is stored. Invalid JSON or a non-object body also gives 400, never 422. An unknown room id, `nope` or a never-created UUID gives 404 `Room not found` before the email is checked, never 422.
- [ ] `POST /api/follows/unsubscribe` with a stored token returns 200 `{"unsubscribed": true}` and removes the follow; repeating it, or an unknown or empty token, returns 200 `{"unsubscribed": false}`. A missing or non-string `token` gives 400. After unsubscribing, following again returns 201 with a new `id` and token.
- [ ] Neither endpoint changes the room's `last_activity_at`, writes a feed event, or calls `notify`. `uv run pytest` passes, with tests per criterion using a fresh `Store` injected via `app.dependency_overrides[get_store]`.

## Out of scope

- Sending the weekly digest email and the unsubscribe link: [#013](013-api-weekly-digest.md). Live stream hook: [#011](011-api-live-sse.md) (follows send no `change`). Frontend wiring: [#014](014-api-frontend-wiring.md).

## Constraints

- Code in `backend/app/routers/follows.py` (registered in `routers/__init__.py`), tests in `backend/app/test_follows.py`. Use `StoreProtocol` via `Depends(get_store)`, `StoredFollow.to_public()` for responses, `ApiError` for errors. Email check is a plain regex; no new dependencies (so no `email-validator`). Follow `_docs/testing-guidelines.md`.

## Original request

**What:** `POST /rooms/{roomId}/follows` and `POST /follows/unsubscribe`, as defined in `openapi.yaml`.
**Why:** People can follow a room by email to get a weekly digest. Sending the digest is out of scope and moved to 013.
**Edge cases:** The email is trimmed and lowercased. Following again with the same email (ignoring case) returns 200 with the existing follow, and a new follow returns 201. An invalid email returns 400 `That email doesn't look right`. The response must never contain the unsubscribe token (`additionalProperties: false`), so add a test that checks this. Unsubscribe is idempotent and returns `unsubscribed: false` for an unknown token. Following does not bump `last_activity_at` or the live stream. An unknown room returns 404.

## Comments
