# [audit] Infrastructure hygiene and a real health check

## Goal

Builds are reproducible, the compose binary is verified, each container gets only its own secrets, tests stay out of the image, and the health check fails when the database is down (`audit.md` 13 bullets 1–4, 14 third bullet).

## Acceptance criteria

- [ ] `Dockerfile` pins `node:24-slim`, `python:3.13-slim` and `ghcr.io/astral-sh/uv` by multi-arch index digest (`name:tag@sha256:…`), and the stack pins `postgres:17-alpine` and `caddy:2-alpine` the same way; the image still builds for linux/arm64; a comment says how to bump a digest (e.g. `docker buildx imagetools inspect`).
- [ ] `infra/ec2-stack.yaml` downloads a fixed docker compose version and checks its SHA-256 for the instance architecture before installing it; a mismatch stops the boot script.
- [ ] Each compose service gets only its own variables: `db` the Postgres password, `app` the database URL, public URL and its other settings (including those from #195 and #203), `caddy` only `SITE_ADDRESS`; files stay mode 600. `docker compose config` shows no password or database URL on `caddy`.
- [ ] The production image holds no `test_*.py` or `conftest.py` (`find /app -name 'test_*'` in the container prints nothing) and the app still starts.
- [ ] `/api/health` runs `SELECT 1` with a short timeout: 200 `{"status": "ok"}` when the database answers, 503 with an `Error` body when it does not. It takes neither the store lock nor the Postgres advisory lock, works on SQLite, and so `infra/deploy.sh`'s health wait only passes with the database up.
- [ ] Tests: health 200; health 503 when the database is unreachable.

## Out of scope

- Getting the compose and env changes onto an already running instance: [#208](208-audit-apply-to-running-instance.md).

## Constraints

- `Dockerfile`, `.dockerignore`, `infra/ec2-stack.yaml`, `backend/app/routers/health.py`, `sql_store.py` (a ping that bypasses the lock).
- After #195 and #203 (they add app env variables). At most 2 tests.

## Comments

**Engineer:** Implemented on branch `worktree-agent-a94920e2dac9089cf`.
- Digests. The `Dockerfile` now pins `node:24-slim@sha256:55fb5f5a…`, `python:3.13-slim@sha256:57b29a7c…` and `ghcr.io/astral-sh/uv:0.13.5@sha256:32a7bb39…`. I pinned uv to a version tag instead of `latest`, because a digest under `latest` would be misleading. 0.13.5 has the same index digest that `latest` had. The stack pins `postgres:17-alpine@sha256:eee6c6e1…` and `caddy:2-alpine@sha256:eb4d35b7…`. All five are multi-arch OCI index digests (amd64 and arm64) from `docker buildx imagetools inspect`. Comments in both files say how to bump a digest. I did not pin the local `docker-compose.yaml`, because it is outside the files this issue names.
- Compose install. `ec2-stack.yaml` downloads docker compose `v5.6.1` (a fixed release, not `latest`) to `/tmp`, checks it with `sha256sum -c` against a hash chosen by `uname -m` (x86_64 or aarch64), then `install`s it. Any other architecture, or a mismatch, stops the boot script (`set -e`). I took the hashes from the release's `checksums.txt` and the per-file `.sha256` assets. I also downloaded both binaries and hashed them myself: x86_64 `47737f42…db8c0` and aarch64 `42cfa75f…1347d`, both matching.
- Env per service. The boot script writes `db.env` (`POSTGRES_PASSWORD`), `app.env` (`FERNSLOP_DATABASE_URL`, `FERNSLOP_PUBLIC_URL`, `FERNSLOP_API_DOCS=0`) and `caddy.env` (`SITE_ADDRESS`). It uses umask 077 and then `chmod 600`. `FORWARDED_ALLOW_IPS` (#195) stays inline on `app`. No `.env` is written any more. The backup script and `fernslop-task@` need nothing else: `docker compose run app` reads `app.env`.
- No tests in the image. `.dockerignore` excludes `**/test_*.py` and `**/conftest.py`. The literal `find /app -name 'test_*'` still found 30 files that third-party packages ship in `.venv` (SQLAlchemy's `testing/suite`, certifi and annotated_types). The runtime never imports them, so the `uv sync` step now deletes `test_*` and `conftest.py` files under `.venv`. That `find` now prints nothing.
- Health. `SqlStore.ping()` runs `SELECT 1` through its own engine with no pool and no `begin` hook, so it takes no store lock, no advisory lock and no SQLite `BEGIN IMMEDIATE`. On Postgres it uses `connect_timeout=3` and `statement_timeout=3s`. My first version pinged a pooled connection, but a hung database (`docker pause`) then left health waiting for more than 30 s. A fresh connection lets libpq's connect timeout cover the whole handshake. `/api/health` returns 200 `{"status": "ok"}`, or 503 `{"message": "The database is not answering."}` on any error, including a store that cannot be built. The main Postgres engine also got `connect_timeout=3`. `ping` was added to `StoreProtocol` in `store.py` (one line).
- Tests (`app/test_main.py`): the existing health 200 test, plus a new test where `FERNSLOP_DATABASE_URL` points at a refused Postgres port and health returns 503 with a message.

Checks:
- `uv run pytest`: 167 passed, 2 skipped. On a throwaway Postgres 17 with `FERNSLOP_TEST_DATABASE_URL`: 169 passed. `uvx ruff check .` passes, and `uvx cfn-lint infra/ec2-stack.yaml` is clean.
- `docker buildx build --platform linux/arm64` builds. In the container, `find /app -name 'test_*'` and `find /app -name conftest.py` print nothing.
- Throwaway compose project `fernslop204check` on port 18204 (pinned postgres plus the arm64 image):
  - health returns 200;
  - while `psql` holds `pg_advisory_xact_lock(7130001)`, health returns 200 in 10 ms and `/api/rooms` blocks;
  - db paused gives 503 in 3.0 s;
  - db stopped gives 503 at once;
  - db restarted gives 200 again.
- The image with `sqlite:////data/fernslop.db` gives health 200 and serves the SPA. I removed all throwaway containers, volumes and images afterwards.
- I rendered the stack's compose file and env files from the template and ran `docker compose config`. caddy has only `SITE_ADDRESS`, db only `POSTGRES_PASSWORD`, and app has the URL, public URL, API docs flag and `FORWARDED_ALLOW_IPS`. All three files are `-rw-------`.
- I ran the compose-install lines from the template on `amazonlinux:2023` arm64. They install `Docker Compose version v5.6.1`, and with one hash character changed they print `FAILED` and exit 1 without installing.

Not checked: a real boot on EC2 (no deploy) and `aws cloudformation validate-template`. The x86_64 branch was checked against the official checksums but not run. Moving an existing instance from `.env` to the new files is #208.

## QA: PASS

- [x] Images pinned by multi-arch index digest, arm64 build, bump comment - PASS
      `docker buildx imagetools inspect --raw` on all five pins (node:24-slim, python:3.13-slim, uv:0.13.5, postgres:17-alpine, caddy:2-alpine) returns an OCI image index that includes linux/amd64 and linux/arm64, and each is the tag's current digest. Bump comments are in the `Dockerfile` and the stack. `docker buildx build --platform linux/arm64` succeeds.
- [x] Fixed compose version, SHA-256 checked per architecture, mismatch stops boot - PASS
      v5.6.1 is pinned. Both hashes match the official v5.6.1 `checksums.txt` and the per-file `.sha256` assets: x86_64 `47737f42…db8c0` and aarch64 `42cfa75f…1347d`. `sha256sum -c` runs under `set -euo pipefail`, and an unknown arch exits 1. I did not run a real EC2 boot.
- [x] Each service gets only its own variables, files mode 600 - PASS
      I rendered the compose and env sections from the template with and without `DomainName` and ran `docker compose config`. caddy gets `{SITE_ADDRESS}` only. db gets POSTGRES_USER, POSTGRES_DB and POSTGRES_PASSWORD. app gets FERNSLOP_DATABASE_URL, FERNSLOP_PUBLIC_URL, FERNSLOP_API_DOCS=0 and FORWARDED_ALLOW_IPS. db.env, app.env and caddy.env are `-rw-------` even when the outer umask is 022. Nothing else in the template still reads `.env`.
- [x] No test_*.py or conftest.py in the image, and the app starts - PASS
      In the arm64 image, `find /app -name 'test_*'` and `find /app -name conftest.py` print nothing. The container starts and serves `/api/health` and `/`.
- [x] /api/health checks SELECT 1 with a short timeout, bypasses the locks, works on SQLite - PASS
      Throwaway compose project `qa204health` on port 18304, using pinned postgres and the arm64 image:
      - DB up: 200 `{"status":"ok"}` in 6 ms.
      - Another session holds `pg_advisory_xact_lock(7130001)`: health returns 200 in 14 ms, while `/api/rooms` blocks until it times out after 4 s.
      - `docker compose pause db`: 503 `{"message":"The database is not answering."}` in 3.0 s.
      - db stopped: 503 in 7 ms.
      - db restarted: 200 again.
      - SQLite (`sqlite:////tmp/qa.db`): 200, and the SPA serves 200.
- [x] Tests: health 200 and health 503 when the database is unreachable - PASS
      `test_health_returns_ok` and `test_health_returns_503_when_the_database_is_unreachable` are in `app/test_main.py`.

Tests: `cd backend && uv sync && uv run pytest`: 167 passed, 2 skipped, 0 failed. `uvx ruff check .`: all checks passed. `uvx cfn-lint infra/ec2-stack.yaml`: clean (exit 0).

Not checked: a real EC2 boot or deploy, and running the x86_64 install branch. Every throwaway container, volume, network and image was removed. The local stack on :8000 was not touched.
