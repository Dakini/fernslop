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
