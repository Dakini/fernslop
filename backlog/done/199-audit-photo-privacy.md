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

## Comments

**Engineer:** Added `pillow` (13.0.0) with `uv add pillow` (`backend/pyproject.toml`, `uv.lock`). `backend/app/uploads.py` has one `strip_metadata(image)` that `upload_photo` calls after `read_image_upload` and before `save_photo` (no store transaction is open). It opens the bytes with Pillow restricted to the sniffed format, refuses (415 `Please use a JPG, PNG or WebP image`) anything Pillow cannot open or fully decode and anything over `Image.MAX_IMAGE_PIXELS`, then scans the raw segments/chunks: JPEG APPn other than JFIF/ICC/Adobe, `COM` or bytes after `EOI`; PNG chunks other than image/colour/animation ones (so `eXIf`, `tEXt`, `iTXt`, `zTXt`, `tIME`, private chunks) or bytes after `IEND`; WebP chunks other than `VP8 /VP8L/VP8X/ALPH/ANIM/ANMF/ICCP` (so `EXIF`, `XMP `). A photo with none of these is stored byte for byte; otherwise it is re-encoded in the same type with `ImageOps.exif_transpose` applied first (JPEG quality 95, WebP lossless if the original was, else quality 90), with only the ICC profile and transparency carried over, and animated PNG/WebP saved with all frames and their durations. Re-encoded output has nothing left to strip, so stripping is idempotent. A multi-picture JPEG (MPO) keeps its first picture. `GET /api/photos/{id}` now also sends `X-Content-Type-Options: nosniff` and `Content-Disposition: inline` (Cache-Control unchanged). `postUpdate` gives 400 `That photo is already in a post` when any feed event in any room (undone ones included, and the seed post) has that photo's URL; since `store.py`/`sql_store.py` are outside this issue, it checks by reading every room's feed through `StoreProtocol` inside the transaction, which is O(all events) per photo post. A `StoreProtocol` lookup by `photo_url` would be cheaper; that's a small follow-up for whoever next touches the store. New `uv run python -m app.photo_strip` lists photo ids straight from the `photos` table (like `photo_cleanup`, it uses a `SqlStore`-only path), strips each one in place (same id, URL, type), prints `Stripped N photo(s)` (plus `, skipped M unreadable` if any stored photo cannot be decoded), and a second run prints 0. The seed photo has no metadata and is left alone. `openapi.yaml` `uploadPhoto` (metadata removal, wider 415), `getPhoto` (no metadata, new headers, backfill) and `postUpdate` (new 400) are updated.
Tests: 5 new. In `test_photos.py`: JPEG with GPS/model/date/Orientation 6 + XMP + comment is stored rotated with no EXIF/XMP/comment; PNG (text, iTXt, eXIf, RGBA) and animated WebP (EXIF, XMP) keep type, alpha and frames with metadata gone; decompression-bomb limit gives 415 and saves nothing. The existing 415 test gained an undecodable-JPEG case, and the existing GET test now checks the two new headers. In `test_posts.py`: the invalid-post test gained a seed-photo reuse case (400, nothing written). New `test_photo_strip.py`: the command strips in place and a second run changes nothing. Existing tests that uploaded fake `\xff\xd8\xff\xe0jpeg-body` bytes now use tiny Pillow-generated images (`test_photos.py`, `test_posts.py`, `test_live.py`), and `test_room_delete.py` makes its shared-photo second post directly through the store, because posting the same photo twice through the API is now refused. Results: `uv run pytest` 140 passed, 2 skipped (Postgres-only); `uvx ruff check .` clean. `docker build --platform linux/arm64` of the full image succeeded, Pillow 13.0.0 with WebP support imports inside it (the throwaway image was removed and the running stack was not touched). The frontend mock does not refuse photo reuse; that is outside this issue. Issue left open.

## QA: PASS

- [x] JPEG with EXIF GPS, camera model, date and Orientation 6 is stored with no EXIF, XMP, IPTC or comment, rotated upright, no Orientation tag - PASS
      Uploaded a 40x20 JPEG with GPS/model/date/Orientation 6, XMP, a COM comment, an APP13 IPTC block and an ICC profile. Served back as JPEG 20x40 with the left red stripe now on top, `getexif()` empty, only APP0 (JFIF) and APP2 (ICC) left, none of the GPS/model/date/XMP/IPTC/comment bytes present.
- [x] PNG (`eXIf`, `tEXt`, `iTXt`) and WebP (EXIF, XMP) are stripped, type kept, transparency kept, animated WebP stays animated - PASS
      RGBA PNG with all three chunks: served as PNG, chunks gone, alpha 0 and 128 pixels intact. Lossy RGBA WebP with EXIF+XMP: served as WebP, chunks gone, alpha kept. 3-frame animated WebP with EXIF+XMP: still 3 frames and animated, metadata gone. Animated PNG also keeps frames and durations.
      Note (not a criterion failure): an animated WebP loses its per-frame timing after re-encoding (sent 100/200/300 ms, stored 100/0/0 ms, since `frame.info["duration"]` is read before the frame is loaded), and a lossless animated WebP is re-encoded lossy (lossless is detected only from a top-level `VP8L` chunk). Worth a follow-up.
- [x] Undecodable bytes past the magic-byte check, or over the decompression-bomb limit, give 415 `Please use a JPG, PNG or WebP image`, store nothing, never 500 - PASS
      JPEG/PNG/WebP magic followed by garbage, a truncated JPEG, and a 12000x12000 PNG (144 MP) all gave 415 with that message; `save_photo` was never called.
- [x] `GET /api/photos/{id}` sends `X-Content-Type-Options: nosniff` and `Content-Disposition: inline`; `Cache-Control` unchanged - PASS
      Headers seen: `nosniff`, `inline`, `public, max-age=31536000, immutable`.
- [x] A post whose `photo_id` is already in a post (including the seed photo) gives 400 `That photo is already in a post` and writes nothing; a fresh upload posts as before - PASS
      Seed photo: 400 with that message, feed event count unchanged. Fresh upload: 201, one event added. Same photo again in a different room: 400, count unchanged.
- [x] `uv run python -m app.photo_strip` strips stored photos in place, prints how many changed, a second run changes nothing - PASS
      Temp SQLite DB with two JPEGs (GPS + Orientation 6) and one WebP with EXIF: first run `Stripped 3 photo(s)`, second run `Stripped 0 photo(s)`; ids, URLs and types unchanged, EXIF empty, JPEG rotated to 20x40.
- [x] `pillow` in `pyproject.toml` and `uv.lock`; arm64 image builds; `openapi.yaml` (`uploadPhoto`, `getPhoto`, `postUpdate`) documents metadata removal and the new 400 - PASS
      `pillow>=13.0.0` in both files. `docker build --platform linux/arm64` succeeded (throwaway tag, removed afterwards; the running stack was not touched), Pillow 13.0.0 with WebP support imports inside it. All three operations describe stripping, the new headers and the new 400/415.

Tests: `cd backend && uv sync && uv run pytest`, 140 passed, 2 skipped, 0 failed
