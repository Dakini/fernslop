PORT ?= 8091

.PHONY: backend backend-dev test install up down delete obs-up obs-down test-frontend test-e2e test-all

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

# What `make up` builds and exports: the version is local-<git short sha>, and traces, metrics and logs go to the
# observability stack. Override on the command line, e.g. `make up OTEL_EXPORTER=none`.
FERNSLOP_IMAGE_TAG ?= local-$(shell git rev-parse --short HEAD)
OTEL_EXPORTER ?= otlp
APP_ENV = FERNSLOP_IMAGE_TAG=$(FERNSLOP_IMAGE_TAG) OTEL_TRACES_EXPORTER=$(OTEL_EXPORTER) \
	OTEL_METRICS_EXPORTER=$(OTEL_EXPORTER) OTEL_LOGS_EXPORTER=$(OTEL_EXPORTER)

# Docker compose stack (Postgres + app on http://localhost:8000, override with APP_PORT), plus the observability
# stack (Grafana on http://localhost:3000) that the app sends its telemetry to
up: obs-up
	$(APP_ENV) docker compose up -d --build --wait

# Stop both stacks, keep their data
down: obs-down
	docker compose down

# Stop both stacks and delete the app's database volume (the observability data is kept)
delete: obs-down
	docker compose down --volumes --remove-orphans

# Only the observability stack (Collector, Tempo, Loki, Prometheus, Grafana), a separate Compose project
obs-up:
	docker compose -f observability/docker-compose.yaml up -d --wait

obs-down:
	docker compose -f observability/docker-compose.yaml down

test-frontend:
	cd frontend && npm test

# Starts its own throwaway copy of the compose stack (see e2e/README.md); leaves `make up` alone
test-e2e:
	cd e2e && uv run pytest

test-all: test test-frontend test-e2e
