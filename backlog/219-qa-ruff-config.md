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
