# [ci] GitHub Actions workflow running backend and frontend tests in parallel

## Goal

A new `.github/workflows/ci.yaml` runs the backend and frontend unit tests as two parallel jobs on every pull request and every push to `main`, and the run goes red if either fails. #226 and #228 will add jobs to this file later.

## Acceptance criteria

- [ ] Triggers are `pull_request` and `push` to `main` only. The workflow sets `permissions: contents: read` and uses no secrets, so PRs from forks also run
- [ ] Job `backend` (working directory `backend/`) installs Python 3.13 and uv `0.13.5`, the versions in `Dockerfile`. It runs `uv sync --locked`, which fails if `uv.lock` is out of date, then `uv run pytest`. It uses the default in-memory SQLite suite, with no Docker and no `FERNSLOP_TEST_DATABASE_URL`
- [ ] Job `frontend` (working directory `frontend/`) installs Node 24 and runs `npm ci` then `npm test`
- [ ] The two jobs have no `needs:` between them, so they run in parallel. Caches are keyed on `backend/uv.lock` and on `frontend/package-lock.json`. Neither job uses `continue-on-error`. Each job has a `timeout-minutes`
- [ ] Every `uses:` is pinned to a full commit SHA, with the version tag in a trailing comment (same style as `Dockerfile`)
- [ ] `concurrency` is grouped by workflow and ref. `cancel-in-progress` is true for pull requests and false for `main`, e.g. `${{ github.event_name == 'pull_request' }}`
- [ ] Verified locally. `actionlint .github/workflows/ci.yaml` reports nothing; it is not installed, so use `brew install actionlint` or `docker run --rm -v "$PWD:/repo" -w /repo rhysd/actionlint:latest`. `cd backend && uv sync --locked && uv run pytest` and `cd frontend && npm ci && npm test` both pass. The engineer comment gives the GitHub run link if pushed, or says no run happened

## Out of scope

- Making these checks required before merging is a repo setting, moved to [#231](parked/231-ci-required-status-checks.md)
- Stack, integration and e2e jobs: #226. Deploy: #228. Python version matrix, lint and coverage: not requested

## Constraints

- Touch only `.github/workflows/ci.yaml`. Do not change `Makefile`, `Dockerfile` or any dependencies
- Actions: `actions/checkout`, `astral-sh/setup-uv` (it can install Python and cache), `actions/setup-node` (`cache: npm`)
- Keep it easy to extend: one top-level `jobs:` map with short, stable job ids (`backend`, `frontend`) that #226 can `needs:`. Put no job-specific settings at workflow level besides `permissions` and `concurrency`
- No new tests. This is config, and running the existing suites is the check

## Comments

**Engineer:** Added `.github/workflows/ci.yaml` (commit 9efc05a). No other file changed, and no tests were added because this is config. **The workflow has not been pushed, so no GitHub Actions run has happened yet.** No run link exists.

- Triggers: `pull_request` and `push` to `main` only. Workflow-level `permissions: contents: read`, and no `secrets.*` are used. Both checkouts set `persist-credentials: false`.
- `backend` job: `defaults.run.working-directory: backend`. `astral-sh/setup-uv` installs uv `0.13.5` and Python `3.13`, the versions in the `Dockerfile`. Then it runs `uv sync --locked` and `uv run pytest`. No `FERNSLOP_TEST_DATABASE_URL`, no services, no Docker.
- `frontend` job: `defaults.run.working-directory: frontend`. `actions/setup-node` installs Node `24`. Then it runs `npm ci` and `npm test`.
- Parallel: there is no `needs:` between `backend` and `frontend`, and there is no `continue-on-error`. Both jobs have `timeout-minutes: 15`. The uv cache is keyed on `cache-dependency-glob: backend/uv.lock`. The npm cache uses `cache: npm` with `cache-dependency-path: frontend/package-lock.json`.
- Pins: I resolved each tag to its commit with `gh api repos/<owner>/<repo>/commits/<tag> --jq .sha`. They are `actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1`, `astral-sh/setup-uv@07a047e608db84b3d8c06cd9a7c7dcc9c355c18e # v10.3.2` and `actions/setup-node@949feb2413d6458794dcd2491c4babbbce0c15c1 # v7.1.0`. These were the latest releases on 2026-10-23. I checked the inputs used against each action's `action.yml` at the pinned SHA.
- Concurrency: `group: ${{ github.workflow }}-${{ github.ref }}` and `cancel-in-progress: ${{ github.event_name == 'pull_request' }}`.
- Workflow level has only `permissions` and `concurrency`, and job ids are `backend` and `frontend`, so #226 can add `needs: [backend, frontend]`.

Local verification:
- `docker run --rm -v "$PWD:/repo" -w /repo rhysd/actionlint:latest -color` printed nothing and exited 0.
- `cd backend && uv sync --locked && uv run pytest` gave 183 passed, 2 skipped, 0 failed. Local Python was CPython 3.13.13 and uv found the lock up to date.
- `cd frontend && npm ci && npm test` gave 10 test files, 56 tests passed, 0 failed. Local Node is v26.3.0 rather than 24, so the Node 24 run will only be confirmed by the first GitHub run.
