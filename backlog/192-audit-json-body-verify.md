# [audit] Verify JSON body cap, Content-Type check and threadpool routes

## Goal

Verify commit `70dd909` (made outside the process; `audit.md` 4 app side, 5 and 9): JSON bodies are capped at 64 KB, only `application/json` is accepted, and no route runs store calls on the event loop. The code is believed done; the engineer fills the gaps: the `openapi.yaml` entries and two missing tests.

## Acceptance criteria

- [ ] Every JSON-body route (`createRoom`, `addPlant`, `movePlant`, `markCare`, `addArea`, `updateArea`, `postUpdate`, `followRoom`, `unfollow`) answers 413 `Request body is too large` for a body over `MAX_JSON_BODY_BYTES` (`backend/app/body.py`), whether sent with `Content-Length` or chunked without it, and writes nothing.
- [ ] Those routes answer 415 `Send the request body as application/json` for `text/plain` or no Content-Type, and accept `application/json; charset=utf-8` and `Application/JSON`.
- [ ] Bodiless calls (`removePlant`, `deleteArea`, `undoEvent`, `deleteRoom`) and the multipart `uploadPhoto` and `identifyPlant` behave as before (a 4.9 MB photo still gives 201).
- [ ] In `backend/app/routers` the only `async def` route is `subscribe` (`/live`), and it calls the store through `run_in_threadpool`.
- [ ] `openapi.yaml` documents the 413 and 415 with their messages on every JSON-body operation (e.g. shared `components/responses`); the frontend shows the message as its toast (already via `errorFrom` in `httpService.ts`, check one).
- [ ] New tests: a chunked body over the cap gives 413; `application/json; charset=utf-8` is accepted.

## Out of scope

- Body limits at Caddy: [#203](203-audit-edge-hardening.md).
- The Postgres advisory lock on every read (rest of audit 5): [parked #206](parked/206-audit-postgres-read-lock.md).

## Constraints

- `openapi.yaml` and tests next to the code (`backend/app/test_rooms.py` or a new `test_body.py`). Change `body.py` only if a criterion fails.
- At most 2 new tests; follow `_docs/testing-guidelines.md` (FastAPI section).

## Comments

**Engineer:** Verified `70dd909`; `body.py` needed no change. Checked every criterion against the running app with a throwaway TestClient script: all nine JSON-body routes give 413 `Request body is too large` for an over-cap body sent with `Content-Length` and chunked, 415 `Send the request body as application/json` for `text/plain` and no Content-Type, accept `Application/JSON` (past the type check), and write nothing in any of those cases. Bodiless routes don't use `JsonBody`, so they're unchanged; a 4.9 MB multipart photo still gives 201. The only `async def` in `backend/app/routers` is `subscribe`, which calls `store.get_room` through `run_in_threadpool`. The frontend's `body()` sends `Content-Type: application/json`, and `errorFrom` in `frontend/src/services/http/httpService.ts` turns `message` into the thrown error the toast shows. Added shared `components/responses` `JsonBodyTooLarge` (413) and `NotJson` (415) to `openapi.yaml`, referenced them from all nine operations, and added a note under Errors (`openapi-spec-validator`: OK). Added 2 tests in `backend/app/test_rooms.py`: a chunked over-cap body gives 413, and `application/json; charset=utf-8` gives 201. `uv run pytest`: 136 passed, 2 skipped. `uvx ruff check .`: clean.

## QA: PASS

- [x] Every JSON-body route answers 413 `Request body is too large` over `MAX_JSON_BODY_BYTES`, with `Content-Length` or chunked, and writes nothing - PASS
      TestClient script: all nine operations gave 413 with that message for a 64 KB + 10 byte body sent with `Content-Length` and as a generator (no `Content-Length` header); a snapshot of every DB table was identical before and after
- [x] 415 `Send the request body as application/json` for `text/plain` or no Content-Type; `application/json; charset=utf-8` and `Application/JSON` accepted - PASS
      All nine gave 415 with that message for both; with the charset and upper-case types every route got past the type check (201/200, or a 400 from field validation on my deliberately minimal bodies), and the DB was untouched by the 415 calls
- [x] Bodiless calls and multipart `uploadPhoto` / `identifyPlant` behave as before - PASS
      `removePlant`, `deleteArea`, `undoEvent`, `deleteRoom` gave 204; a 4.9 MB JPEG upload gave 201 (over 5 MB still 413 `That photo is over 5 MB`); `identifyPlant` gave 200 with matches
- [x] Only `async def` route in `backend/app/routers` is `subscribe`, calling the store via `run_in_threadpool` - PASS
      grep: single `async def` in `live.py`, `await run_in_threadpool(store.get_room, room_id)`
- [x] `openapi.yaml` documents 413 and 415 with their messages on every JSON-body operation; frontend shows the message as its toast - PASS
      Shared `components/responses` `JsonBodyTooLarge` / `NotJson` carry the messages and are referenced from all nine operations; `uvx openapi-spec-validator openapi.yaml`: OK. `errorFrom` in `frontend/src/services/http/httpService.ts` throws `body.message`
- [x] New tests: chunked over-cap body gives 413; `application/json; charset=utf-8` accepted - PASS
      Two new tests in `backend/app/test_rooms.py` cover exactly these

Tests: `cd backend && uv run pytest`, 136 passed, 2 skipped, 0 failed

Note (not a failure): on routes that need `X-Device-Id` / `X-Actor-Name`, a missing header gives its 400 before the 415 type check; 413 is checked first everywhere.
