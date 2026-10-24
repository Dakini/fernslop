# [otel] Backend: OpenTelemetry tracing with service name, environment and version

## Goal

Every API request produces an OpenTelemetry server span whose resource says `service.name`, `deployment.environment.name` and `service.version`, so telemetry shows which service, environment and deployed version it came from. Shipping it anywhere is [#245](../parked/245-otel-export-to-collector.md).

## Acceptance criteria

- [x] With `OTEL_TRACES_EXPORTER=console`, `FERNSLOP_ENVIRONMENT=dev`, `FERNSLOP_IMAGE_TAG=20261023-120000-abc1234`, a `GET /api/health` prints a server span to stdout with resource `service.name=fernslop-backend`, `deployment.environment.name=dev`, `service.version=20261023-120000-abc1234`
- [x] With both variables unset or blank, the resource says `deployment.environment.name=local` and `service.version=unknown`
- [x] `OTEL_SERVICE_NAME` and `OTEL_RESOURCE_ATTRIBUTES` (e.g. `deployment.environment.name=staging`) override the values above
- [x] With no `OTEL_TRACES_EXPORTER` set (local, tests, today's servers), nothing is exported, nothing is logged about a missing collector, and requests behave as today; `OTEL_TRACES_EXPORTER=otlp` uses the standard `OTEL_EXPORTER_OTLP_*` settings so #245 is config only
- [x] `OTEL_SDK_DISABLED=true` turns tracing off entirely; the app still serves requests
- [x] Spans carry no request bodies, headers (`x-device-id`, `x-actor-name`) or response bodies
- [x] At most 5 backend tests in `backend/app/test_telemetry.py`, using an in-memory exporter; the full suite still passes and exports nothing

## Out of scope

- Setting `FERNSLOP_ENVIRONMENT` on the dev and prod containers, [#244](244-otel-environment-in-container.md)
- Choosing a collector or vendor and setting `OTEL_EXPORTER_OTLP_*`, [#245](../parked/245-otel-export-to-collector.md)
- Metrics, logs and database (SQLAlchemy) spans; traces of HTTP requests only

## Constraints

- New module `backend/app/telemetry.py`, called from `create_app()` in `backend/app/main.py`; read `FERNSLOP_IMAGE_TAG` the same way `app/routers/health.py` does (stripped, blank means unset)
- `create_app()` runs once per test: give each app its own `TracerProvider` (pass it to `FastAPIInstrumentor.instrument_app`), never call `trace.set_tracer_provider`, never instrument globally
- Add with `uv add`: `opentelemetry-sdk`, `opentelemetry-instrumentation-fastapi`, `opentelemetry-exporter-otlp-proto-http`; do not use `opentelemetry-instrument` or change the Dockerfile `CMD`
- Document the variables in the module docstring; `/api/health` response is unchanged; follow `_docs/testing-guidelines.md`
