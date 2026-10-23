# [ci] Build the Docker Compose stack in CI and run integration and e2e tests against it

## Goal

A `stack` job in `.github/workflows/ci.yaml` builds and starts `docker-compose.yaml` once, after `backend` and `frontend` pass. It runs the integration tests and then the `e2e/` Playwright suite against that one stack, and always tears the stack down. "Integration" means the backend suite on the stack's Postgres plus an HTTP check of `/api/health`.

## Acceptance criteria

- [ ] Job `stack` has `needs: [backend, frontend]`, a `timeout-minutes` (30 is enough), no `continue-on-error` and no extra `permissions`. Every new `uses:` (e.g. `actions/upload-artifact`) is pinned to a full SHA with the tag in a trailing comment, the same as #225. Checkout uses `persist-credentials: false`
- [ ] A CI-only override `.github/ci/compose.ci.yaml` publishes `db` on `127.0.0.1:55432`. The job runs `docker compose -f docker-compose.yaml -f .github/ci/compose.ci.yaml -p fernslop-ci up -d --build --wait`. Plain `docker compose up` (`make up`) behaves exactly as before
- [ ] Health check: `curl` retries `GET http://localhost:8000/api/health` for up to about 60s and fails the job unless it gets 200 with `{"status":"ok"}`. The body is printed on failure
- [ ] Backend on Postgres: the job creates a separate database (`docker compose ... exec -T db createdb -U fernslop fernslop_test`). From `backend/`, using the same setup-uv settings as job `backend`, it runs `uv sync --locked` and then `uv run pytest` with `FERNSLOP_TEST_DATABASE_URL=postgresql+psycopg://fernslop:fernslop@localhost:55432/fernslop_test`. The run reports 0 skipped, so the two `requires_postgres` tests in `app/test_sql_store.py` ran. The app's `fernslop` database is never wiped
- [ ] E2E: from `e2e/` the job runs `uv sync --locked` and `uv run playwright install --with-deps chromium`, which matches the `playwright==1.63.0` pin. Then it runs `uv run pytest` with `E2E_BASE_URL=http://localhost:8000`, so the suite uses this stack and does not start its own `fernslop-e2e` stack. All 3 e2e test files pass
- [ ] On failure, an `if: failure()` step writes `docker compose ... logs` to a file and uploads it as an artifact. An `if: always()` step runs `docker compose ... down --volumes --remove-orphans`
- [ ] Verified locally without pushing. `docker run --rm -v "$PWD:/repo" -w /repo rhysd/actionlint:latest` reports nothing. The same compose, health, backend and e2e commands pass on the engineer's machine, followed by teardown. The engineer comment pastes the pass/skip counts and says whether a GitHub run happened

## Out of scope

- Playwright traces and screenshots as artifacts. The suite records none today (`e2e/conftest.py` does not use pytest-playwright), so adding them means changing e2e code. Moved to [parked/232-ci-e2e-failure-traces.md](parked/232-ci-e2e-failure-traces.md)
- Building or testing the arm64 production image. CI runners build amd64 from the same multi-arch base digests in `Dockerfile`; arm64 is #228's concern
- Deploy: #228. Required status checks: [#231](parked/231-ci-required-status-checks.md)

## Constraints

- Touch only `.github/workflows/ci.yaml` and the new `.github/ci/compose.ci.yaml`. Do not change `docker-compose.yaml`, `Dockerfile`, `Makefile`, `e2e/`, `backend/` or any dependencies
- Use the fixed project name `fernslop-ci` and the default `APP_PORT` 8000. Locally, use `APP_PORT` or `-p` to avoid clashing with a running `make up`
- No new tests. This is config, and running the existing suites is the check. See `_docs/testing-guidelines.md` ("Running the backend suite on Postgres", "End-to-end") and `e2e/README.md`
- Open question (does not block): the user has not confirmed the TM's definition of "integration" (backend suite on the stack's Postgres plus `/api/health`)

## Engineer

Commit d843071. Changed only `.github/workflows/ci.yaml` (new job `stack`, plus the header comment) and the new `.github/ci/compose.ci.yaml`.

- Job `stack`: `needs: [backend, frontend]`, `timeout-minutes: 30`, no `continue-on-error`, no job `permissions`, checkout with `persist-credentials: false`. The new `uses:` is `actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9 # v7.0.2`, resolved with `gh api repos/actions/upload-artifact/commits/v7.0.2 --jq .sha`. Checkout and setup-uv reuse #225's pins and settings
- `.github/ci/compose.ci.yaml` only adds `127.0.0.1:55432:5432` to `db`. `docker-compose.yaml` is unchanged, so `make up` behaves as before
- Health: 30 tries, 2s apart, each with `curl --max-time 2`. It needs HTTP 200 and `jq -e '.status == "ok"'`. On failure it prints the last status and body
- Backend on Postgres: `createdb -U fernslop fernslop_test` via `exec -T db`, then `uv sync --locked` and `uv run pytest` with `FERNSLOP_TEST_DATABASE_URL` pointing at `fernslop_test`. The step also fails if the pytest summary contains "skipped", which enforces the 0-skipped criterion
- E2E: `uv sync --locked`, `uv run playwright install --with-deps chromium` and `uv run pytest` with `E2E_BASE_URL=http://localhost:8000`
- `if: failure()` writes `docker compose ... logs --no-color` to `stack-logs.txt` and uploads it as artifact `stack-logs`. `if: always()` runs `down --volumes --remove-orphans`

Local verification (macOS, Docker Desktop), with no push:
- `docker run --rm -v "$PWD:/repo" -w /repo rhysd/actionlint:latest -color` printed nothing and exited 0
- I ran the workflow's commands with `-p fernslop-ci`, and with `APP_PORT=8001` because the user's own `fernslop` stack holds 8000. `up -d --build --wait` brought db and app to healthy. The health check got 200 `{"status":"ok"}` after one reset connection on the first try. `createdb` succeeded
- Backend on Postgres: 185 passed, 0 skipped, 0 failed. The SQLite run in #225 had 183 passed and 2 skipped, so the 2 `requires_postgres` tests ran. The app's `fernslop` database still had its 8 tables afterwards
- E2E: 5 passed, 0 skipped, 0 failed, across all 3 files (`test_not_found.py` 1, `test_post_photo.py` 3, `test_shared_garden.py` 1). Chromium came from `uv run playwright install chromium`. I skipped `--with-deps` on macOS
- Teardown: `down --volumes --remove-orphans` removed the containers, `fernslop-ci_pgdata` and the network. The user's `fernslop` project and its volumes were not touched

No GitHub Actions run happened, because nothing was pushed. That leaves `--with-deps` on ubuntu-latest, the default port 8000 and the artifact upload unconfirmed until the first run.

## QA: PASS

Reviewed `git diff main...HEAD`. Only `.github/workflows/ci.yaml`, the new `.github/ci/compose.ci.yaml` and this issue file changed.

- [x] `stack` has `needs: [backend, frontend]`, `timeout-minutes: 30`, no `continue-on-error`, no `permissions`. Checkout uses `persist-credentials: false`. `actions/upload-artifact@cf430e0... # v7.0.2` matches `gh api repos/actions/upload-artifact/commits/v7.0.2 --jq .sha`. Checkout and setup-uv reuse #225's pins - PASS
- [x] The override only adds `127.0.0.1:55432:5432` to `db`, and the job runs the exact `up -d --build --wait` command. `docker-compose.yaml` is unchanged, so `make up` behaves as before - PASS
- [x] Health: 30 tries x 2s with `--max-time 2`, needs 200 plus `jq -e '.status == "ok"'`. Against the real stack it got `{"status":"ok"}` after one reset connection. I ran the same loop against a dead port: it exited 1 and printed the last status (000) and the body - PASS
- [x] Backend on Postgres: `createdb` via `exec -T db`, the same setup-uv settings as `backend`, `uv sync --locked`, then `uv run pytest` against `.../fernslop_test`. A grep on "N skipped" fails the step, and the default bash pipefail catches a pytest failure behind `tee`. My run: 185 passed, 0 skipped. The app's `fernslop` db still had 8 tables afterwards - PASS
- [x] E2E: `uv sync --locked`, `playwright install --with-deps chromium`, `uv run pytest` with `E2E_BASE_URL=http://localhost:8000`. My run (with `E2E_BASE_URL` on 8001, without `--with-deps` on macOS): 5 passed across all 3 files - PASS
- [x] `if: failure()` writes the logs to `stack-logs.txt` and uploads them as `stack-logs`. `if: always()` runs `down --volumes --remove-orphans` - PASS
- [x] actionlint (Docker, `-color`) printed nothing and exited 0. Engineer comment has the counts and says no GitHub run happened - PASS

Tests: `run-stack.sh` with `-p fernslop-ci` and `APP_PORT=8001`. Compose up healthy, health OK, backend on Postgres 185 passed and 0 skipped, e2e 5 passed. Teardown removed `fernslop-ci` containers, `fernslop-ci_pgdata` and the network. The user's `fernslop` project and volumes were untouched.

Not verified (needs a real GitHub run): `--with-deps` on ubuntu-latest, port 8000 inside CI, and the artifact upload on failure.

PASS
