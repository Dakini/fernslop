# [audit] Follow-up: compress photos in the browser before upload
**What:** Before `uploadPhoto` and `identifyPlant`, downscale large photos in the browser (e.g. longest side 2048 px, JPEG quality about 0.85) so phone photos over 5 MB upload instead of failing with 413, as `_docs/lovable-spec.md` asks ("compressed client-side first").
**Why:** Moved out of #190: the user's report that uploading an image "doesn't seem to work" was not reproduced with small files, and recent phone photos are often over 5 MB.
**Edge cases:** Photos stay upright (browsers apply EXIF orientation when drawing; check iOS Safari); PNG transparency; small files are sent unchanged; the server's 5 MB limit and messages stay as they are; memory on low-end phones with 48 MP photos; the mock service path.
