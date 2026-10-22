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
