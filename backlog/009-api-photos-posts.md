# [api] Photos and feed posts

## Goal

`POST /api/photos`, `GET /api/photos/{photoId}` and `POST /api/rooms/{roomId}/posts` behave as `openapi.yaml` defines (`uploadPhoto`, `getPhoto`, `postUpdate`); photos are kept through the store so [#015](015-api-persistence.md) can swap the storage.

## Acceptance criteria

- [ ] `POST /photos` with a valid JPEG, PNG or WebP returns 201 `{id, url}` with a new UUID4 `id` and `url == "/api/photos/{id}"`. Validation is only `read_image_upload` from `uploads.py` (413, 415 and missing-`file` 400 as in [#005](done/005-api-plants.md)); a rejected upload stores nothing. No actor headers needed.
- [ ] `GET /photos/{id}` returns the exact bytes with the sniffed content type and `Cache-Control: public, max-age=31536000, immutable`; the seeded photo works too. An unknown or non-UUID id gives 404 `Photo not found`, never 422.
- [ ] `POST /rooms/{id}/posts` with `{"text": "  Hi  ", "photo_id": null}` returns 201 and a `FeedEvent` of type `post` with `text` `Hi`, `photo_url`, `room_plant_id` and `undo_payload` null, the actor's name and device id, a new UUID4 `id`; it is first in `GET /rooms/{id}` `feed`. A missing `text` or `photo_id` counts as empty; extra fields (such as `photo_url`) are ignored.
- [ ] With a `photo_id` from `POST /photos`, `photo_url` equals that photo's `url`. A photo with no text is valid (`text` `""`), and one photo may be posted several times (photos are not tied to a room).
- [ ] 400, with nothing written, for: empty text and no photo (`Write something or add a photo`); a non-string `text`; text over 1000 characters after trimming (`Text must be at most 1000 characters`); a `photo_id` that is unknown, non-UUID or not a string (`That photo didn't upload — try again`, even when text is present); invalid JSON or a non-object body. Never 422. An unknown or non-UUID room gives 404 `Room not found`.
- [ ] The post requires the actor headers (400 without, as in [#003](done/003-api-actor-auth.md)). A success saves the event and sets the room's `last_activity_at` to the event's `created_at` in one `store.transaction()`, then calls `live.notify(room_id)` once; no failure bumps activity or notifies.
- [ ] `uv run pytest` passes, with tests per criterion using a fresh `Store` via `app.dependency_overrides[get_store]`, including a post that reads back the bytes of a photo it just uploaded.

## Out of scope

- Cleaning up photos that are never posted, and durable photo storage: [#015](015-api-persistence.md). The live stream behind `notify`: [#011](011-api-live-sse.md). Frontend wiring: [#014](014-api-frontend-wiring.md).

## Constraints

- Implement the post endpoint after [#006](006-api-room-plants.md), which creates `backend/app/live.py` with a no-op `notify(room_id)`; call it as `live.notify(...)` after the transaction, as 006 does. Code in `backend/app/routers/photos.py` and `routers/posts.py` (registered in `routers/__init__.py`), `Photo` model in `models.py`, tests in `test_photos.py` and `test_posts.py`. Reuse `uploads.py`; reach photos only via `StoreProtocol` `save_photo`/`get_photo` and `StoredPhoto`; use `Depends(get_actor)`, `ApiError`, `app.timestamps.now()`. No new dependencies; follow `_docs/testing-guidelines.md`.

## Original request

**What:** `POST /photos` stores the image bytes in memory and returns `{id, url: "/api/photos/{id}"}`. `GET /photos/{id}` serves the bytes. `POST /rooms/{roomId}/posts` creates a `post` event. **Why:** This lets people post updates and photos to a room's feed.
**Edge cases:** Uploads have the same 413/415 rules as identify, so share that validation with 005. GET returns the original content type with long public cache headers, and 404 for an unknown photo. Post text is trimmed. If both text and photo are empty, return 400 `Write something or add a photo`. An unknown `photo_id` returns 400 `That photo didn't upload — try again`. The server copies `photo_url` from the stored photo and never takes it from the client. A post has `undo_payload: null`. Photos are not tied to a room. Cleaning up orphaned photos is out of scope and moved to 015.

## Comments
