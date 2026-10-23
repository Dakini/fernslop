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
