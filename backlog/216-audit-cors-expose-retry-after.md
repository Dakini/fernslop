# [audit] Expose `Retry-After` to cross-origin callers

## Goal

When the frontend calls the backend cross-origin (`VITE_API_BASE_URL` set to an absolute URL), the browser can read `Retry-After` on a 429, so the toast says "Try again in N ..." instead of "Try again in a moment".

## Acceptance criteria

- [ ] A cross-origin request from an allowed origin (`FERNSLOP_CORS_ORIGINS` or the defaults) gets `Access-Control-Expose-Headers` that includes `Retry-After`, on 429s and other responses alike.
- [ ] A request from an origin that is not allowed still gets no CORS headers, as today.
- [ ] With Vite on another port and `VITE_API_BASE_URL` pointing straight at the backend, a used-up bucket toasts "Try again in N ..." with the real wait.

## Out of scope

- Nothing moved out. Same-origin setups (Vite proxy, Caddy in prod) already work.

## Constraints

- `backend/app/main.py` (`expose_headers=["Retry-After"]` on `CORSMiddleware`) and `backend/app/test_main.py`. Size: small. At most 1 test.

## Comments

**Engineer:** Added `expose_headers=["Retry-After"]` to `CORSMiddleware` in `backend/app/main.py`. Added one test in `backend/app/test_main.py` (`test_cors_exposes_retry_after_to_allowed_origins`). `uv run pytest`: 176 passed, 2 skipped. `uvx ruff check .` is clean.

- Criterion 1: an allowed origin gets `Access-Control-Expose-Headers: Retry-After` on every response, including 429s. It is set by the new test and was seen on both the 201 and the 429 in the browser check below.
- Criterion 2, a note on the wording: Starlette adds `Access-Control-Expose-Headers` whenever a request has an `Origin` header, allowed or not. It still sends no `Access-Control-Allow-Origin` to an origin it doesn't allow, so the browser blocks that response just as before and the extra header gives the caller nothing. `test_cors_rejects_unknown_origin` still passes. Removing the header for disallowed origins would take a `CORSMiddleware` subclass, which goes beyond the one-line change in the constraints, so I didn't add one. If QA or the PM reads "no CORS headers" literally, this needs a decision.
- Criterion 3: I ran the backend on :8790 (SQLite in the scratchpad, `FERNSLOP_CORS_ORIGINS=http://localhost:5190`, `FERNSLOP_RATE_LIMIT_CREATE_ROOM=1/hour`) and `vite dev` on :5190 with `VITE_API_BASE_URL=http://localhost:8790/api`. In headless Chromium (Playwright) I created two gardens. The first POST returned 201. The second returned 429, and the toast read "You're going a bit fast. Try again in 60 minutes." Both servers were stopped afterwards.
