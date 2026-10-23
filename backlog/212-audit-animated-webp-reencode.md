# [audit] Animated WebP keeps frame timing and lossless encoding after metadata strip

## Goal

An animated WebP that #199 re-encodes to drop its metadata plays at its original speed and, if it was lossless, stays lossless. QA on #199 found stored durations of 100/0/0 ms for frames sent as 100/200/300 ms (`frame.info["duration"]` is read before the frame is loaded), and lossless detection only looks at a top-level `VP8L` chunk, which an animation keeps inside `ANMF`.

## Acceptance criteria

- [ ] A 3-frame animated WebP with EXIF and durations 100/200/300 ms is stored with 3 frames, durations 100/200/300 ms, the same loop count, and no EXIF.
- [ ] A lossless animated WebP with EXIF is stored lossless (decoded frames are pixel-identical to the source frames); a lossy one stays lossy. Static WebP, PNG and JPEG are stored as today.
- [ ] `python -m app.photo_strip` run twice on such a photo changes nothing the second time.

## Out of scope

- None.

## Constraints

- `backend/app/uploads.py` (`_reencode`, `_webp_is_lossless`), `backend/app/test_photos.py`. If frames mix lossy and lossless, save lossless (quality over size). At most 2 tests (extend the existing animated WebP test).

## Comments

**Engineer:** Implemented in `backend/app/uploads.py` without changing the acceptance criteria. In `_reencode`, each animation frame is now copied (and so loaded) before its `duration` is read. Pillow fills a WebP frame's `info` only on load, which is why durations came out as 100/0/0. `_webp_is_lossless` now also looks inside each `ANMF` chunk, skipping its 16-byte frame header, for a `VP8L` chunk. If any picture or frame is lossless, the whole animation is saved lossless, so a mix of lossy and lossless frames is saved lossless. A new helper, `_webp_chunk_spans`, returns each chunk's type and payload, and `_webp_chunks` now uses it. Static WebP, PNG and JPEG go through the same code as before.

Tests in `backend/app/test_photos.py` (2 in total):
- Extended the existing PNG and animated WebP test. The WebP is now a 3-frame lossless animation with EXIF and XMP, durations 100/200/300 ms and loop 3. The test checks that the stored file has those durations, loop 3, no EXIF or XMP, and frames pixel-identical to the source. Running `strip_metadata` again on the stored bytes, which is what `python -m app.photo_strip` does per photo, returns them unchanged.
- Added `test_upload_of_lossy_animated_webp_with_exif_stays_lossy`. The stored bytes contain `VP8 ` and neither `VP8L` nor `EXIF`.

Checks: with the old `uploads.py`, the extended test fails with `[100, 0, 0] == [100, 200, 300]`. With the fix, `cd backend && uv run pytest` gives 167 passed and 2 skipped, and `uvx ruff check .` passes. I also checked by hand that a lossy animated WebP keeps its durations and loop 3 and stays lossy, and that a second strip is a no-op.
