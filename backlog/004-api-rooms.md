# [api] Rooms: list, create, get state
**What:** `GET /rooms`, `POST /rooms` and `GET /rooms/{roomId}`, as defined in `openapi.yaml`.
**Why:** These power the index page and the room page.
**Edge cases:** Trim all fields. A name that is empty or only whitespace returns 400 `A room needs a name`. Enforce max lengths of 60/200/60. Two rooms with the same name are allowed. `last_activity_at` starts at `created_at`. The list is sorted by `last_activity_at`, newest first, and its summaries contain only live plants and areas. The state includes the full feed, newest first, including undone events. An unknown or non-UUID `roomId` returns 404 with an `Error` body, not FastAPI's 422.
