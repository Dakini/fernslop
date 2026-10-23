# [qa] Testing guidelines describe this repo, not Django

## Goal

`_docs/testing-guidelines.md` describes how tests work in this FastAPI + TanStack repo, so engineers and QA stop flagging it: pytest in `backend/app/test_*.py`, vitest in `frontend/src`, Playwright in `e2e/`. Medium (docs only).

## Acceptance criteria

- [ ] No mention of Django, `app/pytest.ini`, `pytest-django`, `reverse()`, `core/` or `AGENT.md`; every command, path and fixture named exists in the repo and runs as written.
- [ ] Backend: how to run all / one file / one test from `backend/`, `conftest.py`'s `reset_store` and `client` fixtures, `{"message"}` error assertions, the Postgres run and `requires_postgres` (keep the existing section).
- [ ] Frontend: `npm test` (vitest, jsdom, `VITE_USE_MOCK`, `src/test/setup.ts`), where `*.test.ts(x)` files live, and testing against the mock service.
- [ ] E2E: how to run `e2e/` (own stack, `E2E_BASE_URL`), linking `e2e/README.md` rather than repeating it.
- [ ] The rules that still hold (naming, Arrange/Act/Assert, test observable behaviour, the per-issue test budget from `_docs/process.md`) and `uvx ruff check .` as the lint step are kept.

## Out of scope

- The outdated `uv run pytest core/tests.py` line in `AGENTS.md`: open question for the user, not changed here.

## Constraints

- `_docs/testing-guidelines.md` only, under about 200 lines. Check each command by running it. After #219 (the ruff step). No tests.

## Comments

**Engineer:** Rewrote `_docs/testing-guidelines.md` (184 lines) from the real config, fixtures and tests. All Django content is gone. It now has an overview table of the three suites with the `make` targets, the per-issue test budget, shared rules (naming, Arrange/Act/Assert, observable behaviour, banners, comments), then Backend, Frontend, End-to-end and Lint sections. With the user's approval (via the orchestrator), the one-file example in `AGENTS.md` now reads `uv run pytest app/test_posts.py` (from `backend/`). Nothing else in `AGENTS.md` changed. No tests (docs).

- Criterion 1: `grep -niE "django|pytest.ini|reverse\(|core/|AGENT\.md"` matches only `[tool.pytest.ini_options]`, the real pyproject section name. I ran every command in the doc: `uv run pytest` (179 passed, 2 skipped), `uv run pytest app/test_posts.py` (20 passed), `uv run pytest app/test_main.py::test_health_returns_ok` (1 passed), the Postgres run in a throwaway `fernslop-pg` container on port 55432 (181 passed, so the `requires_postgres` tests ran too), `npm test` (53 passed), `npx vitest run src/lib/image.test.ts` (2 passed), `npx vitest run -t "returns null for an unknown room"` (1 passed), `cd e2e && uv sync && uv run pytest` (4 passed, on its own `fernslop-e2e` stack; the user's `fernslop` stack was not touched), and `uvx ruff check .` ("All checks passed!"). `npm run test:watch` is the existing script, and I did not run it because it is interactive.
- Criterion 2: run all, one file and one test from `backend/`. Covers the `reset_store`, `reset_rate_limit` and `client` fixtures; injecting a store via `dependency_overrides` (as `test_posts.py` does); `{"message"}` assertions with 400 for validation and 422 only for `markCare`; and the Postgres section with `requires_postgres`, kept and extended with a note never to point it at the compose database.
- Criterion 3: `npm test` with the `vitest.config.ts` settings (jsdom, globals, `VITE_USE_MOCK=true`, `@/` alias, `src/test/setup.ts`). Unit tests sit next to the module, and page and routing tests live in `src/test/`. To test against the mock, use `createMockService({ storage: memoryStorage(), ... })` or `setServices(...)` with a reset in `afterEach`. `httpService` is tested with a stubbed `fetch`.
- Criterion 4: `cd e2e && uv sync && uv run pytest`. It starts its own stack, `E2E_BASE_URL` points it at a running one, and it links `e2e/README.md` for the rest.
- Criterion 5: naming, AAA, observable behaviour and the test budget from `_docs/process.md` are kept, with `uvx ruff check .` from the repo root as the lint step.

## QA: PASS

- [x] No Django leftovers; every command, path and fixture exists and runs - PASS
      `grep -niE "django|pytest\.ini|pytest-django|reverse\(|core/|AGENT\.md"` matches only line 52, `[tool.pytest.ini_options]` (the real section in `backend/pyproject.toml`). Ran every command (results below). Spot-checked with grep: `reset_store`/`reset_rate_limit` (autouse), `client`, `requires_postgres`, `FERNSLOP_TEST_DATABASE_URL`, `DROP SCHEMA public CASCADE` in `backend/conftest.py`; `testpaths`/`pythonpath`/`[tool.ruff]` in `backend/pyproject.toml`; `jsdom`, `globals`, `VITE_USE_MOCK`, `@` alias, `src/test/setup.ts` in `vitest.config.ts`; `test`/`test:watch`/`lint` scripts; `make test|test-frontend|test-e2e|test-all`; `scrollTo`/`matchMedia`/jest-dom in setup.ts; all 12 named files exist; `store`/`api` fixtures, `dependency_overrides`, `make_jpeg`, `post(api, room_id, body`, both banners and the example test name in `test_posts.py`; `createMockService({ storage: memoryStorage(), seed: false, now` in `mockService.test.ts`; `setServices(null)` in `confirm-follow.test.tsx`; stubbed `fetch` in `httpService.test.ts`; 422 only for `markCare` (`errors.py`, `room_plants.py`).
- [x] Backend: all/one file/one test, fixtures, `{"message"}` assertions, Postgres + `requires_postgres` - PASS
      Steps match `conftest.py`. Ran the Postgres run in a throwaway `fernslop-pg-qa220` container on :55491, then removed it: 181 passed, 0 skipped.
- [x] Frontend: `npm test`, vitest config, file locations, mock-service testing - PASS
- [x] E2E: run from `e2e/`, own stack, `E2E_BASE_URL`, links `e2e/README.md` - PASS
      Matches the README and `e2e/conftest.py` (`fernslop-e2e` project, free port, `down --volumes`). Ran it: 4 passed, and the stack was removed afterwards.
- [x] Kept rules (naming, AAA, observable behaviour, test budget) and `uvx ruff check .` - PASS
      Budget matches `_docs/process.md` (5 per issue, 2 small, none for config). The doc is 184 lines.
- [x] `AGENTS.md`: `git diff 08bf929 -- AGENTS.md` shows only the one-file example line changed, to `uv run pytest app/test_posts.py` (from `backend/`)

Tests (all run from the worktree):
- `backend/`: `uv run pytest` 179 passed, 2 skipped; `uv run pytest app/test_posts.py` 20 passed; `uv run pytest app/test_main.py::test_health_returns_ok` 1 passed; Postgres run 181 passed
- `frontend/`: `npm test` 53 passed (10 files); `npx vitest run src/lib/image.test.ts` 2 passed; `npx vitest run -t "returns null for an unknown room"` 1 passed, 52 skipped. I did not run `npm run test:watch` because it is interactive.
- `e2e/`: `uv sync && uv run pytest` 4 passed
- Repo root: `uvx ruff check .` "All checks passed!"

fernslop-app-1, fernslop-db-1 and :8000 were not touched. Nothing in the code or docs was changed.
