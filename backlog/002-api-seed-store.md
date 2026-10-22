# [api] In-memory store with seed data

## Goal

The `Store` in `backend/app/store.py` holds every collection the API needs (plant reference table, rooms, room plants, areas, feed events, photos, follows) in memory, starts out filled with the frontend's 51 plants and three demo rooms, and can be reset to that exact seed in one call. All access goes through a small, named method set (`StoreProtocol`) so routers never touch the underlying containers and [#015](015-api-persistence.md) can swap in a database-backed implementation without touching routers.

## Acceptance criteria

Decisions made here (so the engineer does not have to guess)

- Plant ids are the frontend's ids, produced by the frontend's `slug` rule: lowercase the common name, replace each run of characters outside `a-z0-9` with `-`, strip leading and trailing `-` (so `Chilli Pepper` is `plant-chilli-pepper`).
- Every other seeded id (rooms, room plants, areas, feed events, photos) is a UUID string derived with `uuid.uuid5` from a fixed namespace constant plus a readable key (for example `room:elm-street`), so ids are identical after every `reset()` and every restart, and the demo room URLs `/r/{id}` stay bookmarkable. New rows created at run time by later issues use `uuid.uuid4()`.
- Seed timestamps are computed relative to a `now` value, not hard-coded, so care timers and "x days ago" look live. `reset()` passes `timestamps.now()`; tests pass a fixed `now`.
- The store never raises "not found" and never enforces room limits or business rules: lookups return `None` or an empty list, and routers decide the 404/409 ([#004](004-api-rooms.md) to [#011](011-api-live-sse.md)).
- No follows are seeded. Nothing in the UI reads them, and a fake subscriber would receive real digest emails once [#013](013-api-weekly-digest.md) exists. The follows collection exists and starts empty.

Record models (in `backend/app/models.py`, all subclass `ApiModel`; field names, nullability and enums exactly as in the matching `openapi.yaml` schema)

- [ ] `models.py` defines `Plant`, `Room`, `RoomPlant`, `RoomArea`, `UndoPayload` (the three `kind` variants, discriminated on `kind`), `FeedEvent` and `RoomFollow`. `Room`, `RoomPlant`, `RoomArea` and `FeedEvent` use the `Timestamp` type for their timestamp fields, so a dumped record shows `2026-10-22T09:30:00.000Z`-style strings. `category`, `shape`, `colour` and `FeedEvent.type` are `Literal`s with the spec's enum values. `RoomFollow` rejects unknown fields (`additionalProperties: false`).
- [ ] `models.py` also defines the stored-only types: `StoredFollow` (a `RoomFollow` plus `unsubscribe_token: str`) and `StoredPhoto` (`id`, `url`, `content_type`, `created_at`, `data: bytes`). Dumping a `StoredFollow` as a `RoomFollow` leaves the token out.
- [ ] Request-only and response-only shapes (`CreateRoomInput`, `AreaInput`, `AreaPatch`, `RoomSummary`, `RoomState`, `IdentifyCandidate`, `Photo`) are not defined here; the issue that serves each of them adds it. Later issues reuse the models above and do not redefine them.

Store interface (in `backend/app/store.py`)

- [ ] `StoreProtocol` (a `typing.Protocol`, marked `@runtime_checkable`) declares exactly these methods; the in-memory `Store` implements all of them:
  - Plants: `list_plants()`, `get_plant(plant_id)`
  - Rooms: `list_rooms()`, `get_room(room_id)`, `save_room(room)`
  - Room plants: `list_room_plants(room_id, *, include_deleted=False)`, `get_room_plant(room_plant_id)`, `save_room_plant(room_plant)`
  - Areas: `list_areas(room_id, *, include_deleted=False)`, `get_area(area_id)`, `save_area(area)`
  - Feed: `list_feed_events(room_id)`, `get_feed_event(event_id)`, `save_feed_event(event)`
  - Follows: `list_follows(room_id)`, `get_follow_by_email(room_id, email)` (case-insensitive), `get_follow_by_token(token)`, `save_follow(follow)`, `delete_follow(follow_id)`
  - Photos: `get_photo(photo_id)`, `save_photo(photo)`
  - Housekeeping: `transaction()` and `reset()`
- [ ] `save_*` inserts a new record or replaces the existing one with the same `id`; a replaced record keeps its position in listings. `get_*` returns the record or `None` (an unknown id, an empty string or `"not-a-uuid"` all return `None`, never an exception). `list_*` for an unknown `room_id` returns `[]`.
- [ ] `get_room_plant` and `get_area` return soft-deleted rows too (undo needs them); `list_room_plants` and `list_areas` leave soft-deleted rows out unless `include_deleted=True`.
- [ ] Ordering: `list_plants()` keeps the seed order of the frontend table; `list_rooms()`, `list_room_plants()` and `list_areas()` return insertion order; `list_feed_events()` returns newest first by `created_at` (including undone events), with later-saved events first when two share a timestamp. Sorting rooms by `last_activity_at` is [#004](004-api-rooms.md)'s job.
- [ ] The store hands out and keeps copies: mutating an object returned by `get_*` or `list_*` does not change the store until it is passed to `save_*`, and mutating an object after passing it to `save_*` does not change the stored record. (Test: fetch a room, change its name, fetch again, name is unchanged.)
- [ ] `transaction()` is a context manager backed by a re-entrant lock (`threading.RLock`), so nested use in one thread works and two threads cannot be inside it at once. `reset()` takes the same lock. It does not roll back: later issues must validate before they write, which [#008](008-api-undo.md) relies on for atomic undo. A test shows nested `with store.transaction():` does not deadlock.
- [ ] `get_store()` stays the single place that chooses the implementation; it is typed to return `StoreProtocol`. `Store(*, seed: bool = True)` builds a seeded store, and `Store(seed=False)` an empty one; `reset()` returns to whichever the instance was built as. A test uses `app.dependency_overrides[get_store]` with a `Store(seed=False)` on a throwaway route to show an empty store can be injected.
- [ ] Nothing outside `store.py` and `seed.py` reaches into the store's internal containers (no leading-underscore attribute is used elsewhere).

Reset

- [ ] `store.reset()` discards everything created or changed since the last reset and restores the seed. Test: add a room, soft-delete a seeded plant, save a follow, call `reset()`, and see the original seed (same room ids, same live-plant counts, no follows). It can be called repeatedly. The existing autouse `reset_store` fixture in `backend/conftest.py` keeps working unchanged, and two consecutive tests each see the untouched seed.
- [ ] The three scaffold tests in `app/test_main.py` that set throwaway attributes on the store (`store.scratch`, `store.leaky`) are rewritten to use real store data (for example saving a room) to prove the same thing: reset drops changes and state does not leak between tests. They are not deleted.

Seed builder (new file `backend/app/seed.py`)

- [ ] `build_seed(now: datetime)` returns the full seed as plain data (plants, rooms, room plants, areas, feed events, photos, follows). It raises `ValueError` for a naive `now`. `Store.reset()` calls it with `timestamps.now()`. Calling it twice with the same `now` gives equal data (ids and timestamps).

Plant reference table

- [ ] Exactly 51 plants, in the same order as `frontend/src/services/mock/plants-seed.ts`. Per category: herb 10, vegetable 16, flower 13, houseplant 7, shrub 2, tree 3.
- [ ] Every row matches the TS file field for field: `common_name`, `scientific_name` (including `Fragaria × ananassa`), `category`, `description` (including the em dash in `Sweet Pea` and the exact wording elsewhere), and the four `*_every_days` values with `null` kept as `None` (never converted to 0). `image_url` is `None`, `source` is `RHS Grow Your Own (general guidance)`, `source_url` is `https://www.rhs.org.uk/` on every row. The engineer checks this with a throwaway script against the TS file (not committed); QA may do the same.
- [ ] Ids are unique and follow the slug rule above. A test pins the full ordered list of 51 ids, so an accidental rename fails loudly because the frontend caches `GET /plants` forever. Spot checks in the test: `plant-tomato`, `plant-chilli-pepper`, `plant-fiddle-leaf-fig`, `plant-japanese-maple`, `plant-runner-bean`.
- [ ] The plant rows are built once and reused by `reset()`; reset does not read the TS file or any file at run time.

Demo rooms (exactly three, all ids UUIDs, all plant ids pointing at real reference plants)

- [ ] Room A, `Elm Street Allotment`, description `Plot 14 — shared by the whole street.`, region `Bristol, UK`.
  - Areas: `Veg bed` (rect, x 8, y 12, w 40, h 45, colour `soil`) and `Pond` (ellipse, x 62, y 55, w 26, h 30, colour `water`), both live.
  - Live plants: Tomato (18, 25), Courgette (36, 40), Basil (22, 46), Sunflower (70, 22).
  - One soft-deleted plant: Lettuce at (30, 35) with `deleted_at` set.
- [ ] Room B, `Balcony Jungle`, description `Third-floor balcony, south facing.`, region `Leeds, UK`.
  - Live plants: Monstera (30, 50), Chilli Pepper (60, 40), Geranium (75, 65).
  - One live area `Sunny corner` (rect, colour `sage`) and one soft-deleted area `Old planter` (colour `clay`, `deleted_at` set), so area filtering has data. Area numbers are the engineer's choice within the bounds below.
- [ ] Room C, `Orchard Corner`, with an empty `description` and an empty `region` (empty strings, not `None`), so the "empty string when not set" path has data. At least three live plants (use Apple Tree, Blueberry and Japanese Maple) at distinct positions and at least one live area.
- [ ] Bounds across the whole seed: every `x_pct`/`y_pct`/`w_pct`/`h_pct` is within 0 to 100, every area fits its canvas (`x_pct + w_pct <= 100` and `y_pct + h_pct <= 100`), every room has at most 50 live plants and 10 live areas (the demo rooms are far below), and room names are at most 60 characters, descriptions 200, regions 60.
- [ ] The three rooms have different `last_activity_at` values, and each room's `last_activity_at` equals the `created_at` of its newest feed event. No timestamp in the seed is later than `now`, and every room's `created_at` is not later than any of its plants, areas or events.
- [ ] Every live seeded room plant has `added_by_name` set to the name of the person who added it, `nickname` `None`, and `deleted_at` `None`. At least one plant has `last_watered_at` set (Room A's Tomato) and the others have all four `last_*_at` fields `None`, so both the "never cared for" and the "recently watered" paths have data.

Feed events

- [ ] Every seeded room plant (live or soft-deleted) has a `plant_added` event with `room_plant_id` set to it, text `added a <Common Name>` (for example `added a Tomato`), and a `delete_plant` undo payload pointing at that plant. Each seeded area has an `area_changed` event with a `restore_area` payload whose `area` is `null` and `area_id` is that area.
- [ ] Room A also has: a `care_done` event `watered the Tomato` whose `created_at` equals the Tomato's `last_watered_at` and whose `restore_plant` payload snapshot has `last_watered_at` `None`; a `plant_moved` event for the Tomato that is already undone (`undone_at` set, `restore_plant` payload whose snapshot position equals the Tomato's current position, because the undo put it back); a `plant_removed` event for the soft-deleted Lettuce, not undone, with a `restore_plant` payload whose snapshot has `deleted_at` `None` (so it can be restored); and a `post` with text, `undo_payload` `None` and a `photo_url` of `/api/photos/<photo id>` pointing at the seeded photo.
- [ ] Room B has a `post` with text and no photo (`photo_url` `None`, `undo_payload` `None`).
- [ ] Across the seed, all six event types (`plant_added`, `plant_removed`, `plant_moved`, `care_done`, `area_changed`, `post`) appear at least once, at least one event is undone and at least one soft-deleted plant exists. `actor_name` is non-empty and at most 40 characters on every event, and `device_id` is a fixed non-empty string per demo person (use two or three people).
- [ ] Referential integrity: every `room_id` on a plant, area or event is one of the seeded rooms; every `room_plant_id` on an event, and every id inside an undo payload, is a seeded room plant or area; every `plant_id` is in the reference table; every `photo_url` points at a seeded photo; all ids are unique within their collection.

Photo

- [ ] One seeded photo (fixed UUID id, `content_type` `image/png`, `url` `/api/photos/<id>`) whose `data` is a valid 1x1 PNG (starts with the PNG signature `\x89PNG\r\n\x1a\n`). It is referenced by Room A's post. Serving it over HTTP is [#009](009-api-photos-posts.md), so until that lands the URL returns 404.

Tests (new files `backend/app/test_store.py` and `backend/app/test_seed.py`, plus the rewrite in `test_main.py` above)

- [ ] Together they cover every criterion above: protocol conformance (`isinstance(store, StoreProtocol)`); save/get/list for each collection including replace-in-place, unknown ids and unknown rooms; `include_deleted`; the ordering rules; copy semantics; case-insensitive follow lookup, lookup by token, delete; `transaction()` nesting; `Store(seed=False)`; dependency override; reset restoring the seed; `build_seed` determinism and the naive-`now` error; the plant table (count, categories, pinned ids, spot-checked rows including `None` intervals); each demo room's contents; the bounds, timestamp and referential-integrity checks; the PNG signature.
- [ ] `uv run pytest` from `backend/` exits 0 with no test skipped or xfailed, including all 57 scaffold tests (the three rewritten ones count).
- [ ] `GET /api/health` and the scaffold behaviour are unchanged; no new routes are added by this issue, and `/api/openapi.json` lists no new paths.

## Out of scope

- Room endpoints, room sorting, summaries and the 50/10 limit checks on create: [#004](004-api-rooms.md), [#006](006-api-room-plants.md), [#007](007-api-areas.md)
- Plant endpoints, search and the identify stub: [#005](005-api-plants.md)
- The actor header dependency in `auth.py`: [#003](003-api-actor-auth.md)
- Enforcing limits when undo restores a row, and applying undo payloads: [#008](008-api-undo.md)
- Photo upload and download endpoints, the 413/415 rules and orphan cleanup: [#009](009-api-photos-posts.md), [#015](015-api-persistence.md)
- Follow endpoints (the store only provides the methods): [#010](010-api-follows.md); seeded subscribers and the digest email: [#013](013-api-weekly-digest.md)
- Pushing changes to the live stream when the store changes: [#011](011-api-live-sse.md)
- Real persistence (a database-backed `StoreProtocol` implementation, concurrency beyond the in-process lock, surviving restarts): [#015](015-api-persistence.md)
- Making the frontend call the API instead of its own mock seed, and keeping the two plant tables in sync afterwards: [#014](014-api-frontend-wiring.md)
- Replacing the plant table with data from a real provider: [#012](012-api-identify-provider.md)

## Constraints

- Work only inside `backend/app/` (`store.py`, `models.py`, new `seed.py`, new `test_store.py` and `test_seed.py`, and the three scaffold tests in `test_main.py`). `backend/conftest.py` should need no change. Do not edit `openapi.yaml`, anything in `frontend/`, or any other issue file.
- Do not add dependencies: the approved set is fastapi, uvicorn, python-multipart, pytest and httpx, and nothing else is needed (use the standard library: `uuid`, `threading`, `base64`, `typing`, `dataclasses`). Any new dependency needs asking first, per `AGENTS.md`.
- Keep the storage interface free of anything in-memory specific (no returning live containers, no exposing dicts or lists), so a database or fake-backed implementation can satisfy `StoreProtocol` later. Routes in this project are synchronous `def`, so the interface is synchronous too.
- Follow `openapi.yaml` as the contract for every field name, type and enum; follow the `Timestamp` format from the scaffold (`format_timestamp`, `timestamps.now`).
- Follow `_docs/testing-guidelines.md` with its FastAPI adaptation (tests next to the code in `backend/app/`, `test_<subject>_<condition>_<expected outcome>` names, Arrange/Act/Assert, section banners, helper factories local to each test module, no new shared conftest). Run with `uv run pytest` from `backend/`.
- Commit regularly, and leave this issue open with a comment saying what was done.

## Original request

**Title:** [api] In-memory store with seed data

**What:** `store.py` keeps rooms, plants, room plants, areas, feed events, photos and follows in memory. It is seeded with the plant reference table from `frontend/src/services/mock/plants-seed.ts` and 2–3 demo rooms that have plants, areas and feed events.

**Why:** The request asks for an in-memory store with enough seed data for the frontend to show something.

**Edge cases:** Plant ids must stay stable (e.g. `plant-tomato`), because the frontend caches `GET /plants` forever. Room ids are UUIDs. Seed rooms must stay under the limits (50 plants, 10 areas). Include at least one soft-deleted plant and one undone event so the filtering paths have data. Tests need a way to reset the store to a fresh seed between runs.

## Comments
