# [api] Actor headers dependency (`auth.py`)

## Goal

A FastAPI dependency in `backend/app/auth.py` reads `X-Device-Id` and `X-Actor-Name` from a request and hands the route an `Actor` (`device_id`, decoded `name`), or rejects the request with a 400 `{"message": ...}` error. It attributes edits only: it never authorises anything and never looks anything up. The resource issues (#006 to #009) attach it to the actor endpoints.

## Acceptance criteria

Public surface (in `backend/app/auth.py`, replacing the docstring-only module from [#001](done/001-api-scaffold.md))

- [ ] `auth.py` defines `Actor`, a model built on `ApiModel` with two `str` fields, `device_id` and `name`, and a dependency function `get_actor` that returns an `Actor`. Routers use it as `actor: Actor = Depends(get_actor)`. The module docstring is kept but no longer says the dependency is "added in issue 003".
- [ ] `get_actor` does not use the store and does not raise anything other than `ApiError` (from `app/errors.py`), so every rejection already has the `{"message": ...}` shape.
- [ ] The dependency is opt-in per route. A route that does not depend on it works with the actor headers missing, blank or malformed (this is how room creation and following a room, which need no actor, stay working). No global middleware inspects these headers.

Happy path

- [ ] Headers `X-Device-Id: 7b1f0c2e-5d3a-4c6b-9e2f-1a2b3c4d5e6f` and `X-Actor-Name: Anonymous%20Hedgehog` give `Actor(device_id="7b1f0c2e-5d3a-4c6b-9e2f-1a2b3c4d5e6f", name="Anonymous Hedgehog")`.
- [ ] The name is percent-decoded as UTF-8: `Zo%C3%AB%20%F0%9F%8C%BF` gives the name `Zoë 🌿`. A plain ASCII name with no `%` passes through unchanged. A literal `+` stays `+` (it is not turned into a space; only `%20` is a space).
- [ ] Leading and trailing whitespace is trimmed from the decoded name (`%20%20Fern%20` gives `Fern`) and from the device id; whitespace inside the name is kept as is. The `Actor` holds the trimmed values.
- [ ] Header names are case-insensitive (`x-device-id` and `x-actor-name` work), as HTTP requires.
- [ ] `device_id` is not required to be a UUID: any non-blank string up to 64 characters is accepted, and it is stored as sent (the frontend's `useIdentity` sends the placeholder `pending` before localStorage has loaded, so rejecting non-UUIDs would break first render). The server does not check that the same device id always uses the same name, or that the id has been seen before.

Rejections (decision, resolving the open question in the original request: every failure is **400** with the `{"message": ...}` body, never 401/403/422, since this is not authentication). The messages are exact, because the frontend shows them as a toast:

- [ ] `X-Device-Id` missing, empty or whitespace-only gives 400 `{"message": "X-Device-Id header is required."}`.
- [ ] `X-Device-Id` longer than 64 characters (after trimming) gives 400 `{"message": "X-Device-Id must be at most 64 characters."}`. Exactly 64 is accepted.
- [ ] `X-Actor-Name` missing, empty, or blank after decoding and trimming (for example `%20%20` or `%09`) gives 400 `{"message": "X-Actor-Name header is required."}`.
- [ ] `X-Actor-Name` that is not valid UTF-8 once decoded (for example `%FF` or `%C3`) gives 400 `{"message": "X-Actor-Name is not valid percent-encoded UTF-8."}`. It must not produce a 500 or a name containing the replacement character.
- [ ] A decoded name containing a control character (for example `%00` or `%0A`) gives 400 `{"message": "X-Actor-Name contains invalid characters."}`.
- [ ] A decoded, trimmed name longer than 40 characters gives 400 `{"message": "X-Actor-Name must be at most 40 characters."}`. Length is counted in characters (Unicode code points) after decoding, not bytes and not encoded length: 40 characters is accepted, 41 is rejected, and 40 emoji (160 bytes, far over 120 when encoded) is accepted.
- [ ] The `maxLength: 120` on the encoded header in `openapi.yaml` is deliberately not enforced as a separate rule: it would reject legitimate 40-character names in non-Latin scripts, which the frontend produces (`saveNickname` slices to 40 characters, then the browser encodes). The 40-character decoded limit is the only name-length rule.
- [ ] When both headers are bad, the `X-Device-Id` message is returned (device id is checked first). A bad actor never leaves partial state behind: the dependency runs before the route body, so a request that fails here changes nothing in the store.
- [ ] Because the dependency runs before the route body, a missing actor on a route for a room that does not exist returns the 400 actor error, not 404.

Interaction with the rest of the app

- [ ] A CORS preflight (`OPTIONS`) to a route that depends on `get_actor`, sent without the actor headers (preflights never carry them), still returns 200 from the CORS middleware, not 400.
- [ ] The error bodies come from the existing handlers in `app/errors.py`; nothing new is registered in `main.py`, and there is no `{"detail": ...}` body anywhere.
- [ ] The existing 57 tests from [#001](done/001-api-scaffold.md) still pass.

Tests (in `backend/app/test_auth.py`, written per `_docs/testing-guidelines.md` and its FastAPI adaptation)

- [ ] No real actor route exists yet, so the tests build their own throwaway routes: a route using `Depends(get_actor)` that echoes the `Actor` as JSON, and a second route without the dependency, both added to a `FastAPI()` instance created inside the test module (with `register_error_handlers` applied) so that `app.main.app` is not modified. Requests go through `TestClient`. Do not call `get_actor` directly for the HTTP-visible cases.
- [ ] Every bullet under Happy path and Rejections above has at least one test, with the exact status and `message`; boundary pairs (40 vs 41 characters, 64 vs 65 device id characters) have a test on each side. Include the "no dependency, garbage headers, still 200" case, the "both headers bad, device id wins" case, and an assertion that no response body has a `detail` key.
- [ ] The preflight criterion is tested against the real `app` from `app.main` with a throwaway route, as in the existing `test_main.py` CORS tests, or equivalent.
- [ ] `uv run pytest` from `backend/` exits 0 with no skipped or xfailed tests.

## Out of scope

- Attaching `get_actor` to the add, move, remove and mark care endpoints and writing the actor onto feed events and `added_by_name`: [#006](006-api-room-plants.md)
- Attaching it to the area endpoints: [#007](007-api-areas.md)
- Attaching it to the undo endpoint: [#008](008-api-undo.md)
- Attaching it to the post-update endpoint (the photo upload endpoint takes no actor): [#009](009-api-photos-posts.md)
- The frontend sending the headers, percent-encoding the name and not sending the `pending` placeholder id: [#014](014-api-frontend-wiring.md)
- Room creation and following a room: they take no actor and are covered by [#004](004-api-rooms.md) and [#010](010-api-follows.md); this issue only guarantees the dependency stays out of their way.

## Constraints

- Work only inside `backend/`: `backend/app/auth.py` and the new `backend/app/test_auth.py`. Do not edit `openapi.yaml`, `frontend/`, `main.py` or `errors.py`.
- No new dependencies (`backend/pyproject.toml` and `uv.lock` unchanged). Use only the standard library (for example `urllib.parse.unquote` with strict error handling, not `unquote_plus`) and what FastAPI provides.
- Raise `ApiError(400, message)` from `app/errors.py` for every rejection. Declare the two headers as optional in the dependency so FastAPI's own validation does not answer first with a generic `x-device-id: Field required` message; the messages above are the contract.
- Follow `openapi.yaml` "Authentication" and the `ActorName` parameter. These headers attribute edits; they are self-asserted and must never be used to allow or deny an action, and the server must not treat a name or device id as proof of identity.
- Follow `_docs/testing-guidelines.md` (FastAPI adaptation section): test file next to the code, `test_<subject>_<condition>_<expected outcome>` names, Arrange/Act/Assert, `# --- Section ---` banners, helper factories local to the test module, shared fixtures only from `backend/conftest.py`.
- Use `uv` for everything: `uv run pytest`, run from `backend/`.
- Commit regularly, and leave this issue open with a comment saying what was done.

## Original request

**What:** A FastAPI dependency that reads `X-Device-Id` and `X-Actor-Name` on actor endpoints and gives routers the decoded actor. It attributes edits only and does not authorise anything (see the "Authentication" section of `openapi.yaml`).
**Why:** Every room mutation records the actor on its feed event, and `addPlant` also stores it as `added_by_name`.
**Edge cases:** The name arrives percent-encoded UTF-8 and must be decoded. It is at most 40 characters after decoding; the 120-character schema limit applies to the encoded form. The spec doesn't define the response for a missing, blank or oversized header, so the PM should pick one (400 is suggested). Room creation and following a room do not need an actor.

## Comments

### Engineer: implemented

- `backend/app/auth.py`: `Actor(ApiModel)` with `device_id` and `name`, and `get_actor`, which declares both headers optional, checks the device id first, then decodes the name with `urllib.parse.unquote(..., errors="strict")` (no `+` handling), trims, and raises only `ApiError(400, ...)` with the exact messages from the criteria. Control characters are detected with `unicodedata.category == "Cc"`. No store access, no middleware, `main.py` and `errors.py` untouched. Docstring kept without the "issue 003" wording.
- `backend/app/test_auth.py`: 47 tests on a throwaway `FastAPI()` app (with `register_error_handlers`) covering every happy-path and rejection bullet, both sides of the 40/41 and 64/65 boundaries, 40 emoji accepted, device id winning over a bad name, no `detail` key, dependency running before the route body, an opt-in route working with garbage headers, and a CORS preflight against `create_app()` plus a throwaway actor route.
- `uv run pytest` in `backend/`: 104 passed, no skips or xfails. No dependency changes.
- Note: a name that decodes to a control character plus surrounding whitespace only (for example `%0A`) is reported as "required" because trimming removes it first; `%00` and a control character inside the name give "contains invalid characters", as the criteria describe.
