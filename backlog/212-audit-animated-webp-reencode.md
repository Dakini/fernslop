# [audit] Animated WebP keeps frame timing and lossless encoding after metadata strip
**What:** `_reencode` in `backend/app/uploads.py` (from #199) stores animated WebP frame durations as 100/0/0 ms instead of the originals, and re-encodes a lossless animated WebP as lossy (lossless only detected from a top-level `VP8L` chunk).
**Why:** QA on #199 found it; the animation plays wrong and quality drops.
**Edge cases:** static WebP and PNG/JPEG unaffected; keep the strip idempotent.
