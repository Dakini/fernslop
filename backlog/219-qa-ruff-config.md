# [qa] Same ruff result from the repo root and from backend/

## Goal

`uvx ruff check .` gives the same result whether run from the repo root or from `backend/`, because a ruff config says `app` and `conftest` are first-party (QA finding on [#210](done/210-audit-feed-pagination.md)). Small.

## Acceptance criteria

- [ ] `uvx ruff check .` passes from the repo root, and `uvx ruff check .` passes from `backend/`, on the same tree.
- [ ] In both runs `import app...` sorts as first-party in `backend/app/test_sql_store.py` and `backend/conftest.py` (any import order fix is applied once and both runs agree on it).
- [ ] No ruff rule set is added or changed beyond what is needed for the import order; files outside `backend/` are linted as before.

## Out of scope

- None.

## Constraints

- A `[tool.ruff]` section in `backend/pyproject.toml` (e.g. `src = ["."]`), plus any import-order fixes ruff makes. ruff runs via `uvx`, so no dependency is added. No tests (config).

## Comments

**Engineer:** Added a `[tool.ruff]` section to `backend/pyproject.toml` with only `src = ["."]`. Before the change, `uvx ruff check .` (ruff 0.17.2) failed from the repo root with two I001 errors (`backend/app/test_sql_store.py`, `backend/conftest.py`), because from the root `app` and `conftest` were sorted as third-party; from `backend/` it passed. With the config, ruff resolves both as first-party from either directory, and the existing import order in both files is already correct, so no import fixes were needed and no Python file changed. No tests (config).

- Criterion 1: `uvx ruff check .` prints "All checks passed!" from the repo root and from `backend/` on the same tree.
- Criterion 2: both runs now agree that `import app...` (and `conftest`) is first-party; the current order in both files is accepted by both runs.
- Criterion 3: no rule set is selected or changed. I diffed the enabled-rule list from `ruff check --show-settings backend/conftest.py` before and after: identical. Files outside `backend/` (`e2e/`, `.claude/skills/...`) have no new config and are still linted with the defaults (`--show-files` lists them; they pass).
- `cd backend && uv run pytest`: 179 passed, 2 skipped.

## QA: PASS

- [x] `uvx ruff check .` passes from the repo root and from `backend/` on the same tree - PASS
      ruff 0.17.2: "All checks passed!" (exit 0) from both. For comparison, the pre-change tree (HEAD~1, scratch copy) fails from the root with 2 errors, so the config is what fixes it.
- [x] `import app...` sorts as first-party in both runs - PASS
      In a scratch copy outside the repo, I moved `from app import rate_limit, sql_store` into the third-party block of `backend/conftest.py`. Both runs reported the same `conftest.py:1:1: I001`, and `--diff` proposed the same fix from both directories (move `app` back into the first-party section). The current order of `conftest.py` and `app/test_sql_store.py` is accepted by both runs, and no Python files changed.
- [x] No rule set added or changed, and files outside `backend/` are linted as before - PASS
      The diff adds only `[tool.ruff] src = ["."]` to `backend/pyproject.toml`. The `linter.rules.enabled` list from `--show-settings backend/conftest.py` is identical before and after. The full `--show-settings e2e/conftest.py` output is identical before and after. e2e and `.claude/skills` files are still linted.

Tests: `cd backend && uv run pytest`, 179 passed, 2 skipped, 0 failed
