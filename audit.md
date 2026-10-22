# Fernslop security and bug audit

Date: 2026-10-22. Commit audited: `e5f5a69`.

Scope: everything tracked in the repo. The backend (`backend/app`), the frontend
(`frontend/src`), the container and compose files, and the AWS stack under `infra/`.
Method: full read of the backend, routers, store, infra and the frontend's
network, identity and rendering code, plus a probe script run against the app
with an in-memory database to confirm the behaviours marked **confirmed** below.

## Summary

The code is careful in the places that usually go wrong: SQL goes through bound
parameters, the static file handler checks for path traversal, uploads are
sniffed by magic bytes, unsubscribe tokens are generated with `secrets` and never
returned by the API, the container runs as a non-root user and the instance
requires IMDSv2. None of the classic injection bugs were found.

The exposure comes from the product decision that there are no accounts and
nothing is rate limited. Every write endpoint is open to the whole internet,
so a single script can wipe every garden, fill the disk with photos, subscribe
any email address to any garden, and (once an email sender exists) use the
digest job as a phishing relay. Those are the findings to act on first.

| # | Severity | Finding |
|---|----------|---------|
| 1 | High | Anyone can delete every garden with no credentials and no rate limit |
| 2 | High | Unauthenticated 5 MB photo uploads with no quota and no scheduled cleanup fill the disk |
| 3 | High | Anyone can subscribe any email address to any garden, and user text goes unfiltered into the digest email |
| 4 | Medium | Request bodies are unbounded, so a large JSON body exhausts memory on the 1 GB instance |
| 5 | Medium | Async routes run blocking database work on the event loop under a global lock |
| 6 | Medium | Undo ignores event order and silently reverts later changes |
| 7 | Medium | Uploaded photos keep EXIF metadata, including GPS coordinates, and are public by URL |
| 8 | Medium | Unlimited room and post creation, with unpaginated listing, degrades the app for everyone |
| 9 | Low | JSON endpoints ignore Content-Type, so other websites can make visitors' browsers write to the API |
| 10 | Low | Unsubscribe tokens land in uvicorn access logs and so in CloudWatch |
| 11 | Low | Actor identity is self-asserted, so any name can be impersonated |
| 12 | Low | No security headers, and the default deployment is plain HTTP |
| 13 | Low | Infrastructure hygiene: floating image tags, unpinned compose download, DB password handed to Caddy |
| 14 | Low | Smaller bugs: identity parsing, follow enumeration, health check, client IPs, docs exposure |

---

## 1. Anyone can delete every garden (High)

**Where:** `backend/app/routers/rooms.py:105-117`, design stated in `backend/app/auth.py:1-6`.

`DELETE /api/rooms/{id}` requires nothing, not even the actor headers the other
write endpoints ask for. `GET /api/rooms` lists every room id publicly. A
ten-line script removes every garden on the site, including the seed gardens,
which are only re-created when the `meta.seeded` row is missing, so they do not
come back. The delete cascades to plants, areas, feed and follows and there is
no soft delete or backup to restore from. Photos used only by that room are also
hard-deleted. **Confirmed:** the probe deleted a room with a bare `DELETE`.

Impact: total data loss for all users, trivially and anonymously, repeatable
every time the site is re-populated.

Fix options, roughly in order of effort:

- Make delete a soft delete with a retention window, so a wipe can be reversed.
- Require the actor headers on delete and only allow the device that created the room, or a per-room owner secret handed out at creation and stored in the browser.
- Rate limit writes per IP at Caddy (`rate_limit` plugin) or in the app.
- Take nightly Postgres dumps off the instance; the CloudFormation template already notes that replacing the instance loses the data.

## 2. Unauthenticated photo uploads fill the disk (High)

**Where:** `backend/app/routers/photos.py:28-42`, `backend/app/uploads.py:38-56`,
`backend/app/photo_cleanup.py`, `infra/ec2-stack.yaml` (no cron entry).

`POST /api/photos` stores up to 5 MB per request in the `photos` table with no
credentials, no quota and no link to a room. The only reclamation is
`python -m app.photo_cleanup`, which nothing in the deployment runs, so unposted
photos accumulate forever. The instance has a 20 GB root volume shared with
Postgres, Docker images and swap, so on the order of a few thousand requests
takes the site down. Note also that the 5 MB check in `read_image_upload` runs
after Starlette has already received the whole multipart body and spooled it
to a temp file, so a multi-gigabyte upload still consumes bandwidth and
container disk before being rejected.

Fix:

- Put `request_body { max_size 6MB }` on the Caddy `reverse_proxy` block so oversize bodies are refused at the edge.
- Schedule `photo_cleanup` (systemd timer or cron in the user-data script) and shorten its default age.
- Add a per-IP upload rate limit and a global storage ceiling that returns 507 when exceeded.
- Longer term, move photo bytes out of the database to object storage with a lifecycle rule.

## 3. Subscribe anyone, then inject the email (High)

**Where:** `backend/app/routers/follows.py:50-78`, `backend/app/digest.py:84-98`,
`backend/app/routers/rooms.py:72-76`, `backend/app/routers/posts.py:50-55`.

Three things combine here.

1. `POST /api/rooms/{id}/follows` accepts any email address with no confirmation step. Anyone can sign up a stranger for weekly email from this service.
2. The digest subject is `This week in {room.name}` and the body is each event's `text` verbatim. Room names and post text are trimmed and length-checked but control characters are allowed. **Confirmed:** the probe created a room named `Subject\r\nBcc: everyone@example.com` and posted text containing a fake "unsubscribe here" line. With a real SMTP sender a CRLF in the subject is header injection; newlines in the body let an attacker write a convincing phishing message that arrives from the site's own sender address.
3. Anyone can post in any room, so an attacker can follow a victim's address to their own room and author the entire email.

Today the only sender is `ConsoleSender`, so nothing is actually sent, but the
parked issue `backlog/parked/110-api-email-sender.md` will turn this on. Fix
before that lands:

- Double opt-in: send a confirmation link and only create the follow when it is clicked.
- Reject or strip all `Cc`/`Cf` characters in room name, description, region and post text, as `auth.py` already does for actor names, and in the digest escape or indent user text so it cannot look like the system's own lines.
- Move the unsubscribe link above the user content and consider a signed-sender setup.
- Cap follows per room and per email per day.

The same endpoint also leaks whether an address already follows a room: a repeat
follow returns 200 instead of 201 (`follows.py:66-69`). Return 201 both times.

## 4. Unbounded request bodies (Medium)

**Where:** every `_json_object` helper, for example `backend/app/routers/rooms.py:40-47`;
`Dockerfile:44` (uvicorn flags); `infra/ec2-stack.yaml:177-184` (Caddyfile).

Each JSON route does `json.loads(await request.body())` with no size check, and
neither uvicorn nor the Caddyfile sets a body limit. A single request with a
multi-hundred-megabyte JSON body is read into memory and parsed on a
`t4g.micro` with 1 GB of RAM, which is enough to get the app container
OOM-killed. Fix at Caddy with `request_body { max_size 1MB }` on the API path
(photos need the larger limit from finding 2), and in the app read the body
with a cap before parsing.

## 5. Blocking database calls on the event loop (Medium)

**Where:** `backend/app/routers/room_plants.py:113`, `areas.py:92`, `posts.py:41`,
`follows.py:51` and `:82`, `rooms.py:69` (all `async def`), `routers/live.py:21`;
`backend/app/sql_store.py:196-208` (the lock).

The routes that need `await request.body()` were made `async`, but they then
call the synchronous store directly. Every store call takes a process-wide
`RLock` and a database transaction, and on Postgres every transaction, reads
included, takes the same advisory lock. So while a sync route in the thread
pool holds the lock (a room delete, a seed, a slow query under load), any async
route blocks the single event loop, and with it every SSE stream, the health
check and all other requests. Under moderate load this looks like the whole site
freezing for seconds at a time, and an attacker can provoke it by hammering a
slow endpoint. It is not a deadlock, but it is an easy availability problem.

Fix: make those routes plain `def` and accept the body with a Pydantic model or
`Body(...)` so FastAPI reads it, or wrap store work in `run_in_threadpool`. Also
consider whether the advisory lock on every read is needed on Postgres; it
serialises the entire application through one lock.

## 6. Undo ignores event order (Medium, correctness)

**Where:** `backend/app/routers/feed_events.py:52-67`, snapshot taken in
`room_plants.py:183, 206, 239` and `areas.py:72`.

`RestorePlantPayload` holds a full snapshot of the plant as it was before the
event. Undo writes that snapshot back wholesale and does not check that the
event is the most recent one touching that plant. **Confirmed:** move a plant,
water it, then undo the move. The plant goes back to its old position and its
`last_watered_at` returns to `null`, while the `care_done` event still shows as
not undone. The same applies to areas (undoing an old rename reverts a later
move). Since any visitor can undo any event, this is also a way to quietly erase
other people's care records.

Fix: either apply only the fields the event changed (store a diff, not a
snapshot), or refuse to undo an event when a later not-undone event exists for
the same `room_plant_id` or area id, with a 409 the UI can explain.

## 7. Photos are served with EXIF intact and are public by URL (Medium, privacy)

**Where:** `backend/app/uploads.py`, `backend/app/routers/photos.py:45-50`.

Uploads are stored byte-for-byte. Phone photos usually carry GPS coordinates,
device model and timestamps in EXIF. In an app where people photograph their
own garden, that publishes home locations. Photos are reachable by anyone with
the UUID, cached as `immutable` for a year, and the URL is in the public room
feed. Fix: re-encode or strip metadata on upload (Pillow can do this, but
adding a dependency needs agreement per `AGENTS.md`), and add
`X-Content-Type-Options: nosniff` and a `Content-Disposition: inline` header to
the photo response.

## 8. Unlimited rooms and posts, unpaginated reads (Medium, availability)

**Where:** `backend/app/routers/rooms.py:54-65` (`list_rooms`), `rooms.py:91-102`
(`get_room_state`), `posts.py:40-94`.

Room creation needs no headers and has no cap. `list_rooms` loads every room and
then, per room, every plant, every plant's reference row and every area, with
no pagination. `get_room_state` returns a room's entire feed, and posts of
1000 characters can be added without limit. A script creating tens of thousands
of rooms, or a few hundred thousand posts in one room, makes the index page and
that room unusable for everyone and makes the N+1 pattern in `list_rooms` a CPU
problem. Fix: per-IP rate limits, a cap on rooms per device and events per
room, pagination or a hard limit on the feed returned, and one query per table
in `list_rooms`.

## 9. Content-Type is not checked (Low)

**Where:** all `_json_object` helpers; `backend/app/main.py:37-42` (CORS).

Because the routes parse `request.body()` themselves, a `text/plain` POST is
accepted. **Confirmed:** room creation and follow both returned 201 with
`Content-Type: text/plain`. Such requests are "simple" under CORS, so any web
page can make a visitor's browser create rooms, subscribe emails and upload
photos without a preflight, laundering abuse through other people's IP
addresses. The actor-header routes are protected because the custom headers
force a preflight that the CORS allow-list rejects. Fix: require
`application/json` on JSON routes (a 415 otherwise), which is what the normal
`Body()` path would do for you.

## 10. Unsubscribe tokens in logs (Low)

**Where:** `backend/app/digest.py:89-90` (link format), `Dockerfile:44` (uvicorn
default access log), `infra/ec2-stack.yaml:122-127` (logs ship to CloudWatch).

The unsubscribe link is `GET /unsubscribe?token=...`. The SPA catch-all serves
that path from uvicorn, whose default access log writes the full request line
including the query string, and the compose file ships those logs to CloudWatch
with 14-day retention. Anyone with log access can unsubscribe any follower. The
code takes care elsewhere to keep the token out of error logs, so this is an
oversight. Fix: move the token to a fragment (`/unsubscribe#token=`), which the
browser never sends, or disable uvicorn's access log and let Caddy log without
query strings.

## 11. Self-asserted identity (Low, by design, worth stating)

**Where:** `backend/app/auth.py`.

`X-Actor-Name` is a display name anyone can set, so every feed line can be
attributed to anyone. The name filter removes control characters but allows
format characters (zero-width joiners, right-to-left overrides) and homoglyphs,
so "Ada" can be impersonated indistinguishably. This is the documented model,
but it should be in the threat model note for the product, and the `Cf`
category should be filtered alongside `Cc`.

## 12. No security headers, plain HTTP default (Low)

**Where:** `infra/ec2-stack.yaml:177-184, 196-197`, `backend/app/main.py`.

Nothing sets `Content-Security-Policy`, `X-Content-Type-Options`,
`Referrer-Policy`, `Strict-Transport-Security` or `X-Frame-Options`. With no
domain the stack serves plain HTTP on port 80, so device ids and tokens travel
in the clear. The template calls this out as not production, but the default
path is the one people take. Add a `header` block to the Caddyfile and default
to requiring a domain.

## 13. Infrastructure hygiene (Low)

- `Dockerfile:17` pulls `ghcr.io/astral-sh/uv:latest`; `node:24-slim` and `python:3.13-slim` also float. Pin by digest for reproducible, reviewable builds.
- `infra/ec2-stack.yaml:113` downloads the latest docker compose binary from GitHub at boot with no checksum. Pin the version and verify.
- `infra/ec2-stack.yaml:132, 149, 158`: `env_file: .env` is given to all three containers, so Caddy receives the Postgres password and database URL it has no use for. Give each service only its own variables.
- `Dockerfile:30` copies `backend/app` wholesale, so every `test_*.py` ships in the production image. Harmless but needless.
- No backup of the `pgdata` volume. Combined with finding 1 there is no recovery path.
- `Dockerfile:44`: uvicorn runs without `--proxy-headers` and `--forwarded-allow-ips`, so every request appears to come from the Caddy container. You cannot identify an abuser from the logs, which matters for all the rate-limit findings above.

## 14. Smaller bugs

- `frontend/src/lib/identity.ts:24`: the stored identity is `JSON.parse`d and cast without validation. A corrupted or hand-edited value with a missing `name` or `device_id` sends the literal string `undefined` in the headers and every action then fails with a 400 that the UI cannot explain. Validate the shape and regenerate on mismatch.
- `frontend/src/lib/identity.ts:39` vs `backend/app/auth.py:47`: the frontend accepts a nickname containing control characters that the backend rejects, so a pasted name can break all further actions. Apply the same filter client-side.
- `backend/app/routers/health.py`: `/api/health` returns ok without touching the database, so the deploy script's health wait passes while Postgres is down.
- `backend/app/routers/posts.py:69-73`: a post can reference any existing photo id, including another user's not-yet-posted upload or the seed photo. Low impact, but photos could record the uploading device id and be checked.
- `backend/app/main.py:32-34`: Swagger and ReDoc are public. Fine for an open API, but it accelerates the abuse above. Consider disabling in production.
- `backend/app/routers/plants.py:29-39`: `search_plants` returns all matches with no limit. Harmless at 51 plants but will not stay harmless if the table grows.

## Things that were checked and are fine

- Static serving (`backend/app/static.py:33-40`): `..` segments and absolute-path tricks resolve outside the directory and fall through to the SPA shell. The `_shell.html` file is not served directly.
- SQL: SQLAlchemy Core with bound parameters throughout; the one f-string in `sql_store.py:157` interpolates a constant.
- Upload validation: declared type, size, and magic bytes must all agree; SVG is not accepted, so no stored XSS through images.
- Photo ids must parse as UUIDs before the store is queried.
- Error handling: unhandled exceptions return a generic message and log the trace; no stack traces leak.
- Pl@ntNet key: redacted from httpx logs, exceptions re-raised `from None` so the URL with the key does not surface.
- Frontend rendering: all user text goes through React; no `dangerouslySetInnerHTML` outside the shadcn UI primitives, and `photo_url` and `source_url` come from the server.
- AWS: IMDSv2 with hop limit 1, no SSH, SSM only, least-privilege instance role, encrypted EBS, ECR scan on push, Postgres not published outside the compose network.
- CORS: no credentials, explicit origin list, explicit header list.
