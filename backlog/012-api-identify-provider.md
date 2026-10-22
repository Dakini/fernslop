# [api] Follow-up: real third-party plant identification

## Goal
`POST /plants/identify` can use a real HTTP provider, Pl@ntNet, chosen by env config. With no key configured it still uses the stub. Shapes below are from the [Pl@ntNet identify docs](https://my.plantnet.org/doc/api/identify); the endpoint's own contract stays in `openapi.yaml`.

## Acceptance criteria
- [ ] Config: `FERNSLOP_IDENTIFY_PROVIDER=plantnet` plus a non-blank `FERNSLOP_IDENTIFY_API_KEY` makes `get_identify_provider()` return `PlantNetIdentifyProvider`. Any other combination (unset, `stub`, unknown name, missing or blank key) returns the stub, so the 005 tests pass unchanged.
- [ ] Request: one sync `httpx` `POST https://my-api.plantnet.org/v2/identify/all?api-key=<key>` with multipart field `images` (the upload bytes, filename and sniffed type) and `organs=auto`, with a 10 second timeout.
- [ ] Mapping: each `results[]` item becomes a candidate with `confidence` = `score` and the reference plant whose `scientific_name` equals `species.scientificNameWithoutAuthor` (trimmed, case-insensitive). Unmatched items are dropped, a plant matched twice keeps its highest score, and no match at all is `200 []`.
- [ ] Failures raise `IdentifyError` (so the existing 502 and message apply): timeout, connection error, any non-2xx status, a body that is not JSON or lacks `results`. A WebP upload also raises it without calling upstream, because Pl@ntNet takes only JPG and PNG.
- [ ] The key appears only in the upstream request: never in a response body or header, and never in logs or in the `IdentifyError` message or cause (httpx errors include the URL, so raise `from None`). A test with a failing upstream checks the response and `caplog` for the key.
- [ ] Tests build the provider with an `httpx.Client(transport=httpx.MockTransport(...))`; no test touches the network. They cover the request shape (URL, `api-key`, `organs`, file part), mapping (match, drop, duplicate, empty), each failure above, and the env selector.
- [ ] `uv run pytest` from `backend/` exits 0 with nothing skipped or xfailed.

## Out of scope
- Trying the provider against live Pl@ntNet with a real account key: [#100](100-api-identify-live-check.md)

## Constraints
- Work only in `backend/app/identify.py` and `test_identify.py`. Do not edit `openapi.yaml`, `routers/` or `frontend/`; routers keep depending on `get_identify_provider` only.
- No new dependencies (`httpx` is approved). Read config from `os.environ` as `main.py` does for CORS.
- Follow `_docs/testing-guidelines.md`. Commit regularly; leave the issue open with a comment.

## Original request
**What:** Swap the identify stub from 005 for a real plant ID API that uses a server-side key, and map its results to reference-table rows.
**Why:** This was moved out of 005 because the request asked only for an in-memory, seeded backend with no external services.
**Edge cases:** A failing or timed-out upstream returns 502. Results that don't match any reference plant are dropped. The key must never reach the client.

## Comments

### Engineer
Implemented all criteria in `backend/app/identify.py` and `test_identify.py` (no other files, no new dependencies).
- `get_identify_provider()` reads `FERNSLOP_IDENTIFY_PROVIDER` / `FERNSLOP_IDENTIFY_API_KEY` per call; only `plantnet` plus a non-blank key returns `PlantNetIdentifyProvider`, everything else the stub.
- `PlantNetIdentifyProvider(plants, api_key, client=None)` does one sync multipart POST (`images`, `organs=auto`, `api-key` query, 10 s timeout); an injected `httpx.Client` is used in tests via `MockTransport`.
- Mapping by trimmed, case-insensitive scientific name; unmatched or malformed items (including a score outside 0..1) are dropped, duplicates keep the highest score.
- All failures and WebP uploads raise `IdentifyError` `from None`. httpx logs the full request URL at INFO, so a log filter on the `httpx`/`httpcore` loggers redacts `api-key=` values; a test checks `caplog` at DEBUG.
- `uv run pytest` in `backend/`: 683 passed, nothing skipped or xfailed.
