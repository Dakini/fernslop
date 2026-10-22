# [audit] Strip photo metadata and harden photo responses

## Goal

Stored photos carry no metadata (GPS, device, timestamps) and still display upright, photo responses cannot be sniffed as another type, and a post cannot reuse a photo that is already in a post (`audit.md` 7, 14 fourth bullet). Decision (user): Pillow is approved (`uv add pillow`).

## Acceptance criteria

- [ ] A JPEG with EXIF GPS, camera model, date and Orientation 6 is stored with no EXIF, XMP, IPTC or comment, its pixels rotated so it displays upright, and no Orientation tag left (orientation is applied before stripping, e.g. `ImageOps.exif_transpose`). An ICC colour profile may stay.
- [ ] PNG (`eXIf`, `tEXt`, `iTXt`) and WebP (EXIF, XMP) uploads are stripped too; the type stays the same, transparency is kept and an animated WebP stays animated.
- [ ] Bytes that pass the magic-byte check but Pillow cannot decode, or an image over Pillow's decompression-bomb pixel limit, give 415 `Please use a JPG, PNG or WebP image`, store nothing and never a 500.
- [ ] `GET /api/photos/{id}` also sends `X-Content-Type-Options: nosniff` and `Content-Disposition: inline`; `Cache-Control` is unchanged.
- [ ] A post whose `photo_id` is already used by any post (including the seed photo) gives 400 `That photo is already in a post` and writes nothing; a fresh upload posts as before.
- [ ] `uv run python -m app.photo_strip` strips already stored photos in place (same id, URL and type), prints how many changed, and a second run changes nothing.
- [ ] `pillow` is in `backend/pyproject.toml` and `uv.lock`; the arm64 image builds; `openapi.yaml` (`uploadPhoto`, `getPhoto`, `postUpdate`) says metadata is removed and lists the new 400.

## Out of scope

- Recording the uploading device on a photo: needs a `photos` column, so it waits for migrations ([parked #140](parked/140-db-migrations.md)). Unposted uploads are only reachable by their random UUID, so the reuse check covers the realistic case.

## Constraints

- `backend/app/uploads.py` (one strip function, called by `upload_photo` after validation), `routers/photos.py`, `routers/posts.py`, new `app/photo_strip.py`, `openapi.yaml`, `pyproject.toml`, `uv.lock`.
- Image work happens outside the store transaction. The 5 MB limit applies to the upload as sent. Browsers that cached a photo before the backfill keep their copy: accepted.
- At most 5 tests (small generated images, no binary fixtures over a few KB).
