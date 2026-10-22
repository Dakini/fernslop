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
