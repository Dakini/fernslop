PORT ?= 8091

.PHONY: backend backend-dev test install up down delete test-frontend test-e2e test-all

install:
	cd backend && uv sync

# Run the backend on $(PORT) (default 8091). Data lives in the SQLAlchemy database at
# FERNSLOP_DATABASE_URL (default sqlite:///fernslop.db in backend/, created on first use).
backend:
	cd backend && uv run uvicorn app.main:app --port $(PORT)

# Same, with auto-reload on code changes
backend-dev:
	cd backend && uv run uvicorn app.main:app --port $(PORT) --reload

test:
	cd backend && uv run pytest

# Docker compose stack (Postgres + app on http://localhost:8000, override with APP_PORT)
up:
	docker compose up -d --build --wait

# Stop the stack, keep the database volume
down:
	docker compose down

# Stop the stack and delete its database volume
delete:
	docker compose down --volumes --remove-orphans

test-frontend:
	cd frontend && npm test

# Starts its own throwaway copy of the compose stack (see e2e/README.md); leaves `make up` alone
test-e2e:
	cd e2e && uv run pytest

test-all: test test-frontend test-e2e
