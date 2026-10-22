# [api] Scaffold the FastAPI backend in `backend/`

## Goal

A runnable, empty-but-correct FastAPI backend lives in `backend/`: a uv project whose app serves under `/api`, has the module layout every other `api` issue builds on, returns every error in the spec's `{"message": ...}` shape, formats timestamps exactly as the frontend expects, and has pytest wired up so `uv run pytest` passes from `backend/`.

## Acceptance criteria

Project and tooling

- [ ] `backend/pyproject.toml` exists. `uv sync` run in `backend/` succeeds and creates `backend/uv.lock` (committed). `requires-python` is `>=3.12`.
- [ ] Runtime dependencies are exactly `fastapi`, `uvicorn[standard]` and `python-multipart`. The `dev` dependency group is exactly `pytest` and `httpx`. No other dependency is added (ask first, per `AGENTS.md`).
- [ ] `uv run pytest` run from `backend/` exits 0 and runs at least the tests listed below; no test is skipped or xfailed.
- [ ] `uv run uvicorn app.main:app` run from `backend/` starts and serves on `http://127.0.0.1:8000`.
- [ ] Python caches, `.venv`, `.pytest_cache` under `backend/` are not tracked by git (the root `.gitignore` already covers them; confirm with `git status`).

Layout (all inside `backend/app/`, a package with `__init__.py`)

- [ ] `main.py` defines the FastAPI `app` (title `Fernslop API`, version `0.1.0`), registers the error handlers, the CORS middleware and the routers.
- [ ] `models.py`, `store.py` and `auth.py` exist and import without error. `models.py` holds the shared `ApiModel` base class, the `Error` model (`message: str`) and the `Timestamp` type (below). `store.py` holds a `Store` class with a `reset()` method, one module-level instance, and a `get_store()` function usable as a FastAPI dependency; it holds no data yet (seed data is [#002](002-api-seed-store.md)). `auth.py` contains only a module docstring saying the actor dependency is added in [#003](003-api-actor-auth.md).
- [ ] `routers/` is a package (`routers/__init__.py`) that exposes a list of routers which `main.py` includes. It contains no resource routers yet, because each resource router arrives with its own issue (004 to 011). Adding a router later needs only a new module in `routers/` plus one line in that list.
- [ ] Every route is served under the `/api` prefix (matching `servers: [{url: /api}]` in `openapi.yaml`). Nothing is served at `/` or at `/rooms` without the prefix.

Health check

- [ ] `GET /api/health` returns 200 with body `{"status": "ok"}`. It is deliberately not in `openapi.yaml`, so it is registered with `include_in_schema=False`. It is the only endpoint in this issue.

Error shape (decision: every error body is `{"message": "<short human-readable text>"}`, never `{"detail": ...}`)

- [ ] `app/errors.py` defines `ApiError(status_code: int, message: str)`, an exception whose handler returns that status with body `{"message": message}`. Later issues raise it for 404, 409, 422 and so on.
- [ ] A request body or parameter that fails FastAPI validation returns **400** (not 422) with `{"message": "<field>: <reason>"}`, where `<field>` is the last element of the first error's location and `<reason>` its message, for example `name: Field required`. A body that is not valid JSON also returns 400 with a `message`. Decision: the handler is global and always returns 400; the single 422 case in the spec (`markCare`, [#006](006-api-room-plants.md)) raises `ApiError(422, ...)` itself instead of relying on the validation handler.
- [ ] An unknown path (for example `GET /api/nope`) returns 404 with a `{"message": ...}` body. A wrong method on a known path (for example `POST /api/health`) returns 405 with a `{"message": ...}` body. Both come from a handler for Starlette's `HTTPException`; the `message` is never the bare word `Not Found` leaking a `detail` key.
- [ ] An unhandled exception inside a route returns 500 with `{"message": "Something went wrong. Please try again."}`, and the traceback is not included in the body. (Test with a throwaway route added only inside the test, using `TestClient(app, raise_server_exceptions=False)`.)
- [ ] Every error `message` is a non-empty string.

Timestamps

- [ ] `app/timestamps.py` provides `format_timestamp(dt)` and `now()` helpers. `format_timestamp` converts any timezone-aware `datetime` to UTC and returns the exact `YYYY-MM-DDTHH:MM:SS.mmmZ` form: three-digit milliseconds (truncated, not rounded), a literal `Z`, never `+00:00`, never microseconds. Example: `2026-10-22T09:30:00.000Z`. A naive `datetime` raises `ValueError`.
- [ ] `models.py` exposes `Timestamp`, an annotated `datetime` type that serialises through `format_timestamp` in JSON output. A model with a `Timestamp` field and value `datetime(2026, 10, 22, 9, 30, 0, 123456, tzinfo=UTC)` serialises to `"2026-10-22T09:30:00.123Z"`, and a value with zero microseconds serialises to `"2026-10-22T09:30:00.000Z"` (the `.000` is kept). A non-UTC input such as `+02:00` is converted to UTC.
- [ ] Timestamps compare correctly as plain strings: two formatted values in chronological order are also in lexicographic order (test with values spanning a second boundary and a millisecond difference).

CORS

- [ ] Responses to requests with `Origin: http://localhost:5173` or `Origin: http://localhost:8080` (and their `127.0.0.1` equivalents) carry `Access-Control-Allow-Origin` echoing that origin, and a preflight `OPTIONS` with `Access-Control-Request-Method: POST` and `Access-Control-Request-Headers: content-type,x-device-id,x-actor-name` returns 200 allowing those headers and the methods GET, POST, PATCH, DELETE. A request from `Origin: https://evil.example` gets no `Access-Control-Allow-Origin` header.
- [ ] The allowed origins can be overridden by the environment variable `FERNSLOP_CORS_ORIGINS` (comma-separated list); the defaults above apply when it is unset. No wildcard `*` is used. (Decision: 5173 is the Vite default and 8080 is what the Lovable config often picks, so both are allowed rather than guessing.)

Tests

- [ ] `backend/conftest.py` provides the two fixtures described under Constraints, and both are used by the tests below.
- [ ] Tests exist, in `backend/app/test_main.py`, `backend/app/test_errors.py` and `backend/app/test_timestamps.py`, covering every criterion above: health OK; 404 and 405 shape; 400 on validation failure with the `<field>: <reason>` message, on malformed JSON, and a test route proving 422 is not produced by the handler; 500 shape with no traceback; CORS allowed, preflight and rejected origin; env var override; timestamp format (zero ms, non-zero ms, truncation, non-UTC input, naive input rejected, string ordering); store `reset()` gives a fresh `Store` instance state between two tests (second test sees no mutation made by the first).
- [ ] FastAPI's generated docs are served under the prefix: `GET /api/openapi.json` returns 200 and `GET /api/docs` returns 200. `GET /openapi.json` and `GET /docs` (no prefix) return 404.

## Out of scope

- Seed data and the real contents of the store: [#002](002-api-seed-store.md)
- The `X-Device-Id` / `X-Actor-Name` dependency in `auth.py`: [#003](003-api-actor-auth.md)
- Room endpoints and models: [#004](004-api-rooms.md)
- Plant endpoints, search and the identify stub: [#005](005-api-plants.md)
- Room plant endpoints, including the 422 on `markCare`: [#006](006-api-room-plants.md)
- Area endpoints: [#007](007-api-areas.md)
- Undo: [#008](008-api-undo.md)
- Photos and feed posts (this is why `python-multipart` is approved now): [#009](009-api-photos-posts.md)
- Follow and unsubscribe: [#010](010-api-follows.md)
- Server-Sent Events stream: [#011](011-api-live-sse.md)
- Real plant identification provider: [#012](012-api-identify-provider.md)
- Weekly digest email: [#013](013-api-weekly-digest.md)
- Pointing the frontend at the HTTP API: [#014](014-api-frontend-wiring.md)
- Persistent storage: [#015](015-api-persistence.md)

## Constraints

- Work only inside `backend/` (plus the small addition to `_docs/testing-guidelines.md` made by the PM). Do not edit `openapi.yaml` or anything in `frontend/`.
- Dependencies go in `backend/pyproject.toml` via `uv add`; only the five approved above. `uv.lock` is committed.
- Use `uv` for everything: `uv sync`, `uv run pytest`, `uv run uvicorn app.main:app`.
- Follow `openapi.yaml` as the contract: the `/api` prefix, `Error` body, `Timestamp` format.
- Follow `_docs/testing-guidelines.md`, adapted for FastAPI/pytest as follows (it is written for Django; this list wins where they differ, and a short note has been appended to that document):
  - Run tests from `backend/` with `uv run pytest`; a single file with `uv run pytest app/test_main.py`. Config lives in `backend/pyproject.toml` under `[tool.pytest.ini_options]` (`testpaths = ["app"]`, `python_files = ["tests.py", "test_*.py", "*_tests.py"]`) instead of `pytest.ini`.
  - There is no `pytest-django`, no database and no `django_db` marker. Drop every rule about `reverse()`, `django_db`, `Client`, CSRF and `response.context`.
  - HTTP tests use `fastapi.testclient.TestClient` (needs `httpx`) through a `client` fixture. Do not call route functions directly. Because the app has no URL names, tests assert literal paths including the `/api` prefix (for example `"/api/health"`); keep them in one place per test module as a constant if repeated.
  - Because the store is a module-level in-memory singleton, state would leak between tests. `backend/conftest.py` defines an **autouse, function-scoped fixture `reset_store`** that calls `store.reset()` before each test (and `reset()` again after it), and a `client` fixture that builds a `TestClient(app)` after the reset. This single `conftest.py` is the one exception to the guideline "no shared conftest"; helper factories (for example `make_room(**overrides)`) stay local to each test module.
  - Test location, naming (`test_<subject>_<condition>_<expected outcome>`), Arrange/Act/Assert layout with blank lines, `# --- Section ---` banners and the "test observable behaviour" rule apply unchanged. Tests sit next to the code in `backend/app/`.
  - "Validation" tests assert the status code and the `{"message": ...}` body (the FastAPI equivalent of checking `form.errors`); "not found" tests assert 404 with a `message`, never a crash; anything adjacent but deliberately unbuilt gets a test of today's behaviour with a comment naming the issue.
- Commit regularly, and leave this issue open with a comment saying what was done.

## Original request

**Title:** [api] Scaffold the FastAPI backend in `backend/`

**What:** A uv project in `backend/` with a FastAPI app mounted at `/api` (per `openapi.yaml` `servers`), split into `routers/`, `models.py`, `store.py`, `auth.py`, plus pytest wired up so `uv run pytest` runs from `backend/`.

**Why:** Every other `api` issue builds on this layout; the request asks for routers/models/store/auth modules and tests.

**Edge cases:** FastAPI's default validation error is 422 `{detail}`. The spec wants 400 with an `Error` `{message}` body (422 is reserved for `markCare`), so add a global handler for that. Timestamps must be in the exact format `2026-10-22T09:30:00.000Z`, with milliseconds and a `Z`, because the frontend compares them as strings. Add CORS for the frontend dev server. `_docs/testing-guidelines.md` is written for Django, so the PM should adapt it.

## Comments
