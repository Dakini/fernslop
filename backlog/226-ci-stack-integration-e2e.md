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
