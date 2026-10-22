# [api] Follow and unsubscribe
**What:** `POST /rooms/{roomId}/follows` and `POST /follows/unsubscribe`, as defined in `openapi.yaml`.
**Why:** People can follow a room by email to get a weekly digest. Sending the digest is out of scope and moved to 013.
**Edge cases:** The email is trimmed and lowercased. Following again with the same email (ignoring case) returns 200 with the existing follow, and a new follow returns 201. An invalid email returns 400 `That email doesn't look right`. The response must never contain the unsubscribe token (`additionalProperties: false`), so add a test that checks this. Unsubscribe is idempotent and returns `unsubscribed: false` for an unknown token. Following does not bump `last_activity_at` or the live stream. An unknown room returns 404.
