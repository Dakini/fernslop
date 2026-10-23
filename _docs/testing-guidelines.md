# Testing guidelines

How we write and run tests in this repo. Read this before writing tests, per
`AGENTS.md`. There are three suites:

| Suite | Where | Tool | Run from |
|---|---|---|---|
| Backend | `backend/app/test_*.py` | pytest + FastAPI `TestClient` | `backend/` |
| Frontend | `frontend/src/**/*.test.ts(x)` | vitest + Testing Library (jsdom) | `frontend/` |
| End-to-end | `e2e/test_*.py` | pytest + Playwright (Chromium) | `e2e/` |

From the repo root, `make test` (backend), `make test-frontend`, `make test-e2e`
and `make test-all` run the same commands.

## How many tests

Keep tests lean, this is an MVP. `_docs/process.md` sets the budget: at most 5
tests per issue, at most 2 for small work, none for config or a command. Test
the happy path and the one failure that matters, not every edge case, bad
input, or thing the framework already guarantees.

## Rules for every suite

- One behaviour per test. Python test names are full sentences:
  `test_<subject>_<condition>_<expected outcome>`, e.g.
  `test_invalid_post_is_400_with_message_and_writes_nothing`. Vitest `it(...)`
  strings read the same way inside a `describe` block.
- Arrange / Act / Assert, separated by blank lines, in that order, with no
  `given`/`when`/`then` labels:

  ```python
  def test_health_returns_ok(client):
      response = client.get("/api/health")

      assert response.status_code == 200
  ```

- Test observable behaviour (status codes, response bodies, database state,
  what the user sees on screen), not implementation details. Mock internals
  only when there is no other way to observe the behaviour, and say why in a
  comment.
- Group related tests in a file under a comment banner, e.g.
  `# --- Validation ---...` in `backend/app/test_posts.py`.
- Add a short comment when a test's assumption is not obvious, and reference
  the issue number when a gap is deliberate (e.g. `# --- Daily post cap (#210) ---`).

## Backend (pytest)

Tests live next to the code in `backend/app/`, one `test_<module>.py` per
module (`test_posts.py` tests `routers/posts.py`, `test_rate_limit.py` tests
`rate_limit.py`). Config is in `backend/pyproject.toml` under
`[tool.pytest.ini_options]` (`testpaths = ["app"]`, `pythonpath = ["."]`).

Run from `backend/`:

```bash
uv run pytest                                          # the whole suite
uv run pytest app/test_posts.py                        # one file
uv run pytest app/test_main.py::test_health_returns_ok # one test
```

### Fixtures in `backend/conftest.py`

This is the one shared `conftest.py`. It defines:

- `reset_store` (autouse, function-scoped): sets `FERNSLOP_DATABASE_URL` to an
  in-memory SQLite database (`sqlite://`) and closes cached stores before and
  after every test, so each test gets a fresh, seeded database and
  `./fernslop.db` is never touched.
- `reset_rate_limit` (autouse): every test starts with empty rate-limit counts
  and the default limits.
- `client`: a `fastapi.testclient.TestClient(app)` on that fresh store. Go
  through it rather than calling route functions directly, and use literal
  paths including the `/api` prefix (`client.get("/api/health")`).

A test that needs direct access to its store builds `SqlStore("sqlite://")`
and injects it with `app.dependency_overrides[get_store]`, removing the
override afterwards. See the `store` and `api` fixtures at the top of
`backend/app/test_posts.py`. Test-data helpers (`make_jpeg()`,
`post(api, room_id, body)`, ...) and fixtures used by only one file stay in
that test module.

### Asserting errors

Errors are `{"message": ...}` bodies. Assert the status code and the message:

```python
assert response.status_code == 400
assert response.json()["message"] == "Write something or add a photo"
```

Validation failures are 400 (`app/errors.py`). 422 is used only for
`markCare`. When a request is rejected, also assert that nothing was written.

### Running the backend suite on Postgres

`uv run pytest` runs on in-memory SQLite and needs no setup. To run the same
suite on Postgres, start a throwaway container and set
`FERNSLOP_TEST_DATABASE_URL`:

```bash
docker run -d --rm --name fernslop-pg -e POSTGRES_PASSWORD=pw -e POSTGRES_DB=fernslop -p 55432:5432 postgres:17-alpine
cd backend
FERNSLOP_TEST_DATABASE_URL=postgresql+psycopg://postgres:pw@localhost:55432/fernslop uv run pytest
docker stop fernslop-pg
```

With it set, `conftest.py` empties that database before every test (`DROP
SCHEMA public CASCADE`) and points both `FERNSLOP_DATABASE_URL` and every
`SqlStore("sqlite://")` a test builds at it. The test database is wiped, so
never point it at data you care about, and never at the `docker compose`
stack's database. Tests that only make sense on Postgres carry the
`requires_postgres` marker from `conftest.py`
(`from conftest import requires_postgres`, see `app/test_sql_store.py`) and
are skipped when the variable is unset.

## Frontend (vitest)

Run from `frontend/` (after `npm install`):

```bash
npm test                                   # vitest run, the whole suite
npx vitest run src/lib/image.test.ts       # one file
npx vitest run -t "returns null for an unknown room"  # tests whose name matches
npm run test:watch                         # watch mode
```

Config is `frontend/vitest.config.ts`: the `jsdom` environment, vitest globals,
`VITE_USE_MOCK=true` so `getServices()` returns the in-browser mock service
instead of HTTP, the `@/` alias for `src/`, and the setup file
`src/test/setup.ts` (jest-dom matchers, stubs for `window.scrollTo` and
`window.matchMedia`).

Test files match `src/**/*.test.ts(x)`:

- Unit tests sit next to the module: `src/lib/image.test.ts`,
  `src/services/mock/mockService.test.ts`,
  `src/components/garden/DeleteGardenDialog.test.tsx`.
- Page and routing tests live in `src/test/` (`app-routing.test.tsx`,
  `confirm-follow.test.tsx`, ...).

Testing against the mock service:

- Service logic: build a mock directly with
  `createMockService({ storage: memoryStorage(), seed: false, now: () => ... })`
  and call it (see `setup()` in `mockService.test.ts`).
- Components and pages: inject a service with `setServices(...)` from
  `@/services`, passing only the methods the test needs as `vi.fn()`s, and
  reset with `afterEach(() => setServices(null))` (see
  `src/test/confirm-follow.test.tsx`). Assert what the user sees with
  Testing Library queries (`screen.findByText(...)`).
- The HTTP service (`src/services/http/httpService.test.ts`) is tested
  against a stubbed `fetch`, never a running backend.

## End-to-end (Playwright)

Browser tests in `e2e/` run against the real `docker-compose.yaml` stack
(Postgres plus the app serving the built frontend). Run from `e2e/`:

```bash
uv sync
uv run pytest
```

The suite starts its own stack under the compose project `fernslop-e2e` on a
free port and removes it afterwards, so a stack you run by hand is not
touched. Set `E2E_BASE_URL` to test an already running stack instead. See
[`e2e/README.md`](../e2e/README.md) for the other variables, installing
Chromium and what each test covers. Add an e2e test only for a flow that
needs a real browser and backend together (live updates across two
gardeners, photo upload); everything else belongs in the backend or
frontend suite.

## Lint

Run ruff from the repo root before committing:

```bash
uvx ruff check .
```

It checks every Python file in the repo (`backend/`, `e2e/`). Files in
`backend/` use `[tool.ruff]` in `backend/pyproject.toml`; the rest use
ruff's defaults. The frontend has its own `npm run lint` (eslint).
