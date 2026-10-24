# Observability stack

A local OpenTelemetry Collector with Tempo (traces), Prometheus (metrics), Loki (logs) and Grafana.
It is its own Compose project (`fernslop-observability`). Starting or stopping it does not touch the app stack.

```
app --OTLP--> otel-collector --traces--> Tempo      \
                             --metrics-> Prometheus  --> Grafana
                             --logs----> Loki       /
```

## Run it

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

The backend only exports when `OTEL_TRACES_EXPORTER` is set (see `backend/app/telemetry.py`).

Backend on the host (`make backend`):

```sh
OTEL_TRACES_EXPORTER=otlp OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318 make backend
```

App container (`make up`): it already points at `http://host.docker.internal:4318`, so set only the exporter:

```sh
OTEL_TRACES_EXPORTER=otlp make up
```

Then in Grafana go to Explore → Tempo and search for `service.name = fernslop-backend`. Each trace has
`deployment.environment.name` and `service.version`. The backend sends traces only for now. The Prometheus
and Loki pipelines are ready for metrics and logs.

## Files

- `otel-collector.yaml`: receivers, and the exporters to Tempo, Prometheus and Loki. Resource attributes become Prometheus labels
- `tempo.yaml`, `loki.yaml`, `prometheus.yml`: single-node configs with local storage
- `grafana/provisioning/datasources/`: the three data sources, linked so a trace opens its logs
