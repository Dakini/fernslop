# Observability stack

A local OpenTelemetry Collector with Tempo (traces), Prometheus (metrics), Loki (logs) and Grafana.
It is its own Compose project (`fernslop-observability`). Starting or stopping it does not touch the app stack.

```
app --OTLP--> otel-collector --traces--> Tempo      \
                             --metrics-> Prometheus  --> Grafana
                             --logs----> Loki       /
```

## Run it

`make up` starts this stack together with the app, and the app sends it traces, metrics and logs. `make down`
stops both. To run only this stack:

```sh
make obs-up      # or: docker compose -f observability/docker-compose.yaml up -d --wait
make obs-down    # stop, keep data; add --volumes to the compose command to delete it
```

| What | Where |
|---|---|
| Grafana (no login, local only) | http://localhost:3000 (`GRAFANA_PORT` to change) |
| Prometheus | http://localhost:9090 |
| Collector OTLP gRPC / HTTP | `localhost:4317` / `localhost:4318` |

All ports are bound to `127.0.0.1`. Tempo, Loki and Prometheus keep 7 days of data in named volumes.

## Send the app's telemetry to it

`make up` does this for you: it sets the exporters to `otlp`, `FERNSLOP_ENVIRONMENT` to `local` and the version
to `local-<git short sha>`. `make up OTEL_EXPORTER=none` turns exporting off.

Otherwise the backend only exports when `OTEL_TRACES_EXPORTER`, `OTEL_METRICS_EXPORTER` and `OTEL_LOGS_EXPORTER`
are set (see `backend/app/telemetry.py`).

Backend on the host (`make backend`):

```sh
OTEL_TRACES_EXPORTER=otlp OTEL_METRICS_EXPORTER=otlp OTEL_LOGS_EXPORTER=otlp \
  OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318 make backend
```

Traces: Grafana → Explore → Tempo, search `service.name = fernslop-backend`.

Metrics: the **Fernslop → Fernslop app metrics** dashboard shows gardens created, garden plants created,
creation failures, active participants and plant searches with no results. It also shows how many distinct
search terms found nothing, and a table of those terms. Filter it by **Environment** and **Deployed version**
at the top. The metrics are defined in `backend/app/metrics.py` and exported every minute
(`OTEL_METRIC_EXPORT_INTERVAL` in ms to change it). Every series has `deployment_environment_name` and
`service_version` labels.

Logs: only empty plant searches are sent, one log line each with the search term (lower-cased, trimmed, at most
100 characters) as `search_term`. The term is in Loki rather than Prometheus, because one series per term
would grow without limit. Grafana → Explore → Loki:
`{service_name="fernslop-backend"} | scope_name="fernslop.search"`.

## On a server

`infra/obs-deploy.sh` runs this same stack on its own EC2 instance, which dev and prod send their telemetry to.
On top of `docker-compose.yaml` it uses `docker-compose.server.yaml`: Caddy with HTTPS in front, a Grafana login,
and a token for OTLP. See "Observability server" in `infra/README.md`.

## Files

- `otel-collector.yaml`: receivers, and the exporters to Tempo, Prometheus and Loki. Resource attributes become Prometheus labels
- `tempo.yaml`, `loki.yaml`, `prometheus.yml`: single-node configs with local storage
- `grafana/provisioning/datasources/`: the three data sources, linked so a trace opens its logs
- `grafana/dashboards/`: dashboards loaded at start-up (edits made in Grafana are not saved back here)
- `docker-compose.server.yaml`, `Caddyfile.server`: server only (above)
