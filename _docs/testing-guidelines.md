# Testing guidelines

How we write and run tests in this repo. Read this before writing tests, per
`AGENT.md`.

## Running tests

All commands run from `app/` (where `pyproject.toml` and `pytest.ini` live):

- `uv run pytest` - the whole suite
- `uv run pytest core/tests.py` - one test file
- `uv run pytest core/test_auth.py::test_login_success_redirects_to_login_redirect_url` - one test

Config lives in `app/pytest.ini`:

```ini
[pytest]
DJANGO_SETTINGS_MODULE = config.settings
python_files = tests.py test_*.py *_tests.py
```

`pytest-django` provides the Django integration (test database creation/
migration, the `client` fixture, `django_db` marker). It's declared in the
`dev` dependency group in `app/pyproject.toml` alongside `pytest`.

## Where tests live

Tests live next to the code they test, inside each Django app, not in a
top-level `tests/` directory:

- `app/core/tests.py`, `app/core/test_auth.py`, `app/core/test_wait_for_db.py`
- `app/config/tests.py`
- `app/projects/test_projects.py`

Start with a single `tests.py` per app (see `core/tests.py`). Once an app's
tests outgrow one file, split by concern into sibling `test_*.py` files in
the same app directory - e.g. `core/test_auth.py` splits auth tests out of
`core/tests.py`. This works because `pytest.ini`'s `python_files` matches
`tests.py`, `test_*.py`, and `*_tests.py`.

If a single app's tests outgrow even a handful of `test_*.py` files, promote
that app's tests to a `tests/` package (`app/<app>/tests/__init__.py` plus
`test_*.py` modules inside it) rather than continuing to add flat files.
No app has needed this yet - do it when it actually gets unwieldy, not
pre-emptively.

## pytest-django conventions in use

- Mark database-touching test modules with a module-level
  `pytestmark = pytest.mark.django_db` near the top of the file (see
  `core/test_auth.py`, `projects/test_projects.py`) rather than decorating
  every test individually. For a file with only one or two DB tests,
  decorating the function directly with `@pytest.mark.django_db` is fine
  (see `core/tests.py`).
- Use the `client` fixture (function-scoped, provided by `pytest-django`)
  for anything that goes through Django views/middleware - don't call view
  functions directly.
- Use `django.test.Client(enforce_csrf_checks=True)` directly (not the
  `client` fixture, which disables CSRF checks) when a test needs to assert
  CSRF enforcement - see `test_post_register_without_csrf_token_is_rejected`.
- Use `reverse()` for every URL a test needs, including query strings built
  from it (e.g. `f"{reverse('login')}?next={reverse('dashboard')}"`). Do not
  hard-code paths, with one accepted exception: the health check endpoint
  (`/health/`) is asserted as a literal path because it's meant to stay a
  stable, unnamed, infrastructure-level URL.
- Build test data with small helper factory functions local to the test
  module, not fixtures in a shared `conftest.py` (none exists yet) - e.g.
  `make_user(username=..., password=...)` in `projects/test_projects.py`,
  `register_payload(**overrides)` in `core/test_auth.py`. Give them sane
  defaults and accept `**overrides`/keyword args so individual tests only
  specify what they care about.
- Assert against `response.context["form"].errors` to check validation
  failures, not by scraping rendered HTML for error text.

## Test structure and style

- One behavior per test. Test function names are full descriptive sentences:
  `test_<subject>_<condition>_<expected outcome>`, e.g.
  `test_registration_with_duplicate_username_shows_error_not_500`.
- Arrange / Act / Assert, separated by blank lines, in that order - no
  `given`/`when`/`then` comment labels, just the blank-line grouping. Example:

  ```python
  def test_login_success_redirects_to_login_redirect_url(client):
      User.objects.create_user(username="loginuser", email="loginuser@example.com", password=VALID_PASSWORD)

      response = client.post(reverse("login"), {"username": "loginuser", "password": VALID_PASSWORD})

      assert response.status_code == 302
      assert response.url == reverse("dashboard")
  ```

- Group related tests within a file under a comment banner, e.g.
  `# --- Login -----------------------------------------------------------------`.
  See the `# --- Registration ---`, `# --- Login ---`, `# --- Logout ---`
  sections in `core/test_auth.py` and the `# --- Model defaults ---`,
  `# --- Create view: ... ---`, `# --- Detail view ---` sections in
  `projects/test_projects.py`.
- Add a short comment when a test's assumption isn't obvious from the code
  alone, especially when it's deliberately not testing something that looks
  related - e.g. `# No Membership model exists yet (#5), so there is no
  notion of this user being a member - the point of this test is that it
  doesn't matter.` Reference the relevant issue number when the gap is
  intentional and tracked.
- Prefer testing observable behavior (status codes, redirect targets, DB
  state, rendered content, form errors) over implementation details.
  `core/test_wait_for_db.py` is the one place tests mock internals
  (`django.db.utils.connections`) because the thing under test is a retry
  loop around a side-effecting call, not the DB, and there's no other way to
  observe its behavior.

## What to test for models and views (from #4 onward)

Every Django model and view added should get coverage in the app's test
file(s) for at least:

**Models**

- Field defaults (e.g. `test_project_defaults_to_friday_5pm_deadline_rule`).
- Any documented business rule encoded as a default or constraint (or the
  explicit absence of one, e.g.
  `test_two_projects_with_the_same_name_can_coexist` confirming there's no
  uniqueness constraint on `name`).

**Views**

- Auth gating: anonymous `GET` and `POST` are redirected to `login` with the
  correct `?next=` when a view is `@login_required`; anonymous `POST` must
  not create data.
- Happy path: a signed-in user can reach the form (`GET`) and successfully
  submit it (`POST`), including the redirect target and any resulting DB
  state.
- Validation: at minimum, blank/whitespace-only required fields and
  boundary-length fields (one over the max, exactly at the max) are rejected
  with a form error and no DB write - never a 500 or a raw DB exception.
  CSRF is enforced on `POST` (see the `enforce_csrf_checks=True` pattern
  above).
- Not-found handling: an unknown object id returns 404, not a crash.
- Anything explicitly out of scope for the current issue but adjacent (e.g.
  membership checks before #6 exists) should have a test asserting today's
  actual behavior, with a comment explaining what's deliberately not
  checked yet and which issue will add it.

When in doubt, match the density and style already in `core/test_auth.py`
and `projects/test_projects.py` rather than inventing a new pattern.


## FastAPI backend adaptation (`backend/`)

The sections above describe the Django setup. The FastAPI backend in
`backend/` follows the same style with these changes:

- Run from `backend/`: `uv run pytest`, or `uv run pytest app/test_main.py`.
  Config is in `backend/pyproject.toml` under `[tool.pytest.ini_options]`, not
  `pytest.ini`. There is no `pytest-django`, no database and no `django_db`
  marker.
- Use a `client` fixture built on `fastapi.testclient.TestClient` (needs
  `httpx`). Do not call route functions directly. There is no `reverse()`, so
  assert literal paths including the `/api` prefix.
- The store is a SQLAlchemy database chosen by `FERNSLOP_DATABASE_URL`.
  `backend/conftest.py` defines an autouse, function-scoped `reset_store`
  fixture that points that variable at an in-memory SQLite database
  (`sqlite://`) and drops the cached `get_store()` store before and after every
  test, so each test gets a fresh seeded database and `./fernslop.db` is never
  touched, plus the `client` fixture. This is the one shared `conftest.py`;
  test-data factories still live in each test module. A test that needs its
  own store builds `SqlStore("sqlite://")` (or a `tmp_path` file URL when it
  needs a restart or threads) and injects it with
  `app.dependency_overrides[get_store]`.
- Errors are `{"message": ...}` bodies, not forms. Assert the status code and
  `response.json()["message"]` where the Django rules say to check
  `form.errors`. Validation failures are 400 (422 only for `markCare`).
- Naming, Arrange/Act/Assert, section banners and "test observable
  behaviour" apply unchanged. Tests live next to the code in `backend/app/`.

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
never point it at data you care about. Tests that only make sense on Postgres
carry the `requires_postgres` marker from `conftest.py` and are skipped when
the variable is unset.
