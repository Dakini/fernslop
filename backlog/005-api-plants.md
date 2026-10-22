# [api] Plants: list, search, identify (stubbed)

## Goal

`GET /api/plants`, `GET /api/plants/search` and `POST /api/plants/identify` work as in `openapi.yaml` (response shapes and error messages are defined there, not repeated here). Identify uses a deterministic stub behind a small provider interface, and upload validation lives in one shared module that [#009](009-api-photos-posts.md) reuses.

## Acceptance criteria

- [ ] `GET /plants` returns all 51 reference plants in seed order, identical on every call, and needs no actor headers.
- [ ] `GET /plants/search?q=` matches case-insensitively as a literal substring (no regex or wildcard meaning) on `common_name` or `scientific_name`, in table order, with no cap. `q=TOM` finds Tomato, `q=fragaria` finds the strawberry, and `q=zzz` returns `200 []`.
- [ ] `q` is trimmed before matching (`q=%20tom%20` finds Tomato). A missing, empty or whitespace-only `q` returns the first 12 plants.
- [ ] New `backend/app/uploads.py` exposes one function that takes an `UploadFile` and returns the bytes, sniffed content type and filename, or raises `ApiError`. Order of checks: declared type not `image/jpeg`, `image/png` or `image/webp` gives 415; more than 5 × 1024 × 1024 bytes gives 413 (exactly 5 MiB passes, 5 MiB + 1 fails); then the bytes are sniffed (JPEG `FF D8 FF`, PNG 8-byte signature, WebP `RIFF....WEBP`) and a mismatch with the declared type, or unrecognised bytes, gives 415. Messages are the ones in `openapi.yaml`.
- [ ] Edge cases of the validator: an empty (0 byte) file gives 415, `image/jpg` gives 415, a PNG declared as `image/jpeg` gives 415, and a missing `file` field gives the existing 400 `file: Field required`.
- [ ] `POST /plants/identify` validates through that module only (no duplicated checks in the router), and does not store the photo or touch the store.
- [ ] New `backend/app/identify.py` defines `IdentifyProvider` (a `typing.Protocol` with `identify(image) -> list[IdentifyCandidate]`), a `StubIdentifyProvider` built from the reference plants, and a `get_identify_provider()` dependency that returns the stub. [#012](012-api-identify-provider.md) swaps the implementation by changing that one function; routers never import the stub directly.
- [ ] The stub ports the frontend mock (`identifyPlant` in `frontend/src/services/mock/mockService.ts`): `h = 0`; for each UTF-16 code unit of `filename + str(size_in_bytes)`, `h = (h * 31 + unit) mod 2^32`; candidates are `plants[(h + i * 7) % 51]` for `i` 0, 1, 2 with confidence 0.82, 0.11, 0.04; a filename containing `blurry` (any case) divides each confidence by 4. A missing filename counts as `""`. A test pins the three plant ids for one known filename and size (worked out by hand from this rule) and checks that the same upload gives the same answer twice.
- [ ] The response has at most 3 candidates, sorted by confidence descending (a provider returning them unsorted is still sorted by the router), each `{plant, confidence}` with a full `Plant`. An empty list from a provider is a valid `200 []`.
- [ ] If the provider raises `IdentifyError` (defined in `identify.py`), the route returns 502 with the message `We couldn't identify that photo — try again`. A test uses `app.dependency_overrides[get_identify_provider]` with a fake that raises, and another fake that returns unsorted and empty results. Any other exception stays a 500.
- [ ] `IdentifyCandidate` is added to `models.py`; the three routes live in `backend/app/routers/plants.py`, registered in `routers/__init__.py`, and all appear in `/api/openapi.json`.
- [ ] Tests in `test_plants.py`, `test_uploads.py` and `test_identify.py` cover every bullet above, per `_docs/testing-guidelines.md`; `uv run pytest` from `backend/` exits 0 with nothing skipped or xfailed.

## Out of scope

- Calling a real identification API, mapping its results to reference rows, and real upstream failures: [#012](012-api-identify-provider.md)
- Storing and serving photos, and reusing `uploads.py` for `POST /photos`: [#009](009-api-photos-posts.md)
- The frontend calling these endpoints instead of its mock: [#014](014-api-frontend-wiring.md)

## Constraints

- Work only in `backend/app/` (`routers/plants.py`, `routers/__init__.py`, `uploads.py`, `identify.py`, `models.py`, the three test files). Do not edit `openapi.yaml`, `frontend/`, or other issue files.
- No new dependencies (`python-multipart` is already approved); standard library only for sniffing and hashing.
- Read plants via `StoreProtocol` (`list_plants`, via `get_store`); routes are synchronous `def`.
- Follow `_docs/testing-guidelines.md` and its FastAPI adaptation. Commit regularly; leave the issue open with a comment saying what was done.

## Original request

**Title:** [api] Plants: list, search, identify (stubbed)

**What:** `GET /plants`, `GET /plants/search` and `POST /plants/identify`. Identify returns up to 3 candidates from the reference table using a deterministic stub, like the mock's `identifyPlant`, instead of calling a real third-party API.

**Why:** The add-plant flow needs these. The real provider is out of scope and moved to 012.

**Edge cases:** Search is a case-insensitive substring match on common or scientific name. A missing, empty or whitespace-only `q` returns the first 12 plants. A file over 5 MiB (5 × 1024 × 1024) returns 413, and a type other than jpeg/png/webp returns 415, both with the exact messages from the spec. Decide whether the type check trusts the declared content type or sniffs the bytes. Candidates are sorted by confidence, highest first. The 502 path is unused until 012.

## Comments
