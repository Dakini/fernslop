# syntax=docker/dockerfile:1

# --- Stage 1: build the frontend as a static SPA ------------------------------
FROM node:24-slim AS frontend
WORKDIR /frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
# FERNSLOP_STATIC=1 switches vite.config.ts to a client-only build (dist/client/_shell.html).
# The API base URL defaults to /api, which is where the backend serves the API (same origin).
RUN FERNSLOP_STATIC=1 npm run build

# --- Stage 2: Python backend + built frontend ---------------------------------
FROM python:3.13-slim AS runtime
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    FERNSLOP_STATIC_DIR=/app/static \
    FERNSLOP_DATABASE_URL=sqlite:////data/fernslop.db

WORKDIR /app

COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev

COPY backend/app ./app
COPY --from=frontend /frontend/dist/client ./static

RUN useradd --system --create-home --uid 10001 fernslop \
    && mkdir /data && chown fernslop /data
USER fernslop
VOLUME /data
EXPOSE 8000

# One worker: the live SSE feed is in-process (see backlog/parked/090-api-live-multi-worker.md).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
