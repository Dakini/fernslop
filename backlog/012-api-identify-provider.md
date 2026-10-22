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

### QA

## QA: PASS

- [x] Config: plantnet + non-blank key selects `PlantNetIdentifyProvider`; unset, `stub`, unknown, `PlantNet`, empty provider, missing/blank/whitespace key all return the stub - PASS
- [x] Request: one POST to `https://my-api.plantnet.org/v2/identify/all?api-key=<key>`, multipart `images` (bytes, filename, sniffed type) plus `organs=auto`, timeout 10 s on connect/read/write/pool - PASS
- [x] Mapping: score becomes confidence, trimmed and case-insensitive scientific-name match, unmatched dropped, duplicate keeps highest score, no match or empty results is `200 []` - PASS
- [x] Failures: ReadTimeout, ConnectTimeout, ConnectError, 301/401/404/429/500, non-JSON, empty body, JSON without `results`, non-object body, non-list `results` all give `IdentifyError` and 502 via `POST /api/plants/identify`; WebP gives 502 with zero upstream calls - PASS
- [x] Key never leaks: with key `SECRET123`, no occurrence in any response body or header, the `IdentifyError` message or `__cause__` (None, `from None`), the formatted traceback, or any log record at DEBUG (httpx lines show `api-key=***`; httpcore DEBUG lines against a real loopback client carry no URL). Note: `__context__` still holds the httpx error but is suppressed, which is what the criterion asks for - PASS
- [x] Tests use `httpx.MockTransport`, cover request shape, mapping, each failure and the env selector, and check `caplog` for the key; no network - PASS
- [x] `uv run pytest` exits 0, nothing skipped or xfailed - PASS

Tests: `uv run pytest` (backend/), 683 passed, 0 failed. Also ran throwaway scripts (MockTransport, TestClient, loopback server for the real-client log check); no code changed.
