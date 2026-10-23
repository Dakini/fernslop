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
