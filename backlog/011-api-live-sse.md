# [api] Live updates via Server-Sent Events
**What:** `GET /rooms/{roomId}/live` is a `text/event-stream` that sends `event: change` / `data: <roomId>` after every mutation in that room, plus a `: ping` comment roughly every 25 s.
**Why:** It keeps multiple browsers on the same room in sync.
**Edge cases:** It broadcasts on every mutation from 004 to 009, including undo, but not on follow or room creation. An unknown room returns 404 before the stream opens. Subscribers must be cleaned up on disconnect so they don't leak. Each room gets only its own events. Testing a stream with TestClient is awkward, so expose a way to inspect the broadcaster or keep the ping interval configurable for tests.
