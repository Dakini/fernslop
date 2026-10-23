# syntax=docker/dockerfile:1

# Base images are pinned by their multi-arch index digest (tag@sha256:...), so a rebuild uses the same bytes on
# amd64 and arm64. To bump one, read the new index digest and replace it here (and for postgres/caddy in
# infra/ec2-stack.yaml):
#   docker buildx imagetools inspect node:24-slim | grep -m1 Digest

# --- Stage 1: build the frontend as a static SPA ------------------------------
FROM node:24-slim@sha256:55fb5f5a527ea2c5c4a95f963e48ef90aa38c7b346054fdc8ee9957a2b55d205 AS frontend
WORKDIR /frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
# FERNSLOP_STATIC=1 switches vite.config.ts to a client-only build (dist/client/_shell.html).
# The API base URL defaults to /api, which is where the backend serves the API (same origin).
RUN FERNSLOP_STATIC=1 npm run build

# --- Stage 2: Python backend + built frontend ---------------------------------
FROM python:3.13-slim@sha256:57b29a7c050c4e679e4bea572e14b3965cf4b5839de2da49d55e49ffc4024f39 AS runtime
COPY --from=ghcr.io/astral-sh/uv:0.13.5@sha256:32a7bb39b496babbd997b0a39a4d66c126bdaf5661b302bf6f06abda8deca6ff /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    FERNSLOP_STATIC_DIR=/app/static

WORKDIR /app

COPY backend/pyproject.toml backend/uv.lock ./
# Also drop the test modules some packages ship (SQLAlchemy's testing suite, certifi, annotated_types); the app
# never imports them, and the image is meant to hold no test_*.py or conftest.py at all.
RUN uv sync --frozen --no-dev \
    && find /app/.venv -type f \( -name 'test_*' -o -name 'conftest.py' \) -delete

# .dockerignore keeps test_*.py and conftest.py out, so the image holds no tests
COPY backend/app ./app
COPY --from=frontend /frontend/dist/client ./static

RUN useradd --system --create-home --uid 10001 fernslop \
    && mkdir /data && chown fernslop /data
USER fernslop
EXPOSE 8000

# The database is not baked in: pass FERNSLOP_DATABASE_URL (a SQLAlchemy URL) at run time, e.g.
#   -e FERNSLOP_DATABASE_URL=sqlite:////data/fernslop.db -v fernslop-data:/data
# or Postgres (the psycopg driver is installed):
#   -e FERNSLOP_DATABASE_URL=postgresql+psycopg://user:pw@host/db
# /data is writable by the app user so a named volume mounted there works for SQLite.
# One worker: the live SSE feed and the rate limits are in-process (see backlog/parked/090-api-live-multi-worker.md).
# --proxy-headers takes the client IP from X-Forwarded-For, but only from a peer listed in FORWARDED_ALLOW_IPS
# (comma-separated). Behind a reverse proxy set it to the proxy's fixed address; the default trusts nothing
# outside the container, so a client-sent X-Forwarded-For is ignored. Limits: see app/rate_limit.py.
ENV FORWARDED_ALLOW_IPS=127.0.0.1
CMD ["sh", "-c", "[ -n \"$FERNSLOP_DATABASE_URL\" ] || { echo 'FERNSLOP_DATABASE_URL is not set' >&2; exit 1; }; exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips \"$FORWARDED_ALLOW_IPS\""]
