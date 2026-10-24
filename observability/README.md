# Observability stack

A local OpenTelemetry Collector with Tempo (traces), Prometheus (metrics), Loki (logs) and Grafana.
It is its own Compose project (`fernslop-observability`). Starting or stopping it does not touch the app stack.

What each signal records, the key user journey and the privacy rules are in
[`docs/observability.md`](../docs/observability.md). This page is how to run and change the stack.

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
creation failures, photos uploaded, active participants and plant searches with no results. Counts are exact, not
Prometheus's `increase()` estimate. Each app process is its own series (`service_instance_id`), so a panel takes its
highest value in the range minus its value at the start. That still counts a process whose first export failed. It also shows how many distinct
search terms found nothing, and a table of those terms. Filter it by **Environment** and **Deployed version**
at the top. The metrics are defined in `backend/app/metrics.py` and exported every minute
(`OTEL_METRIC_EXPORT_INTERVAL` in ms to change it). Every series has `deployment_environment_name` and
`service_version` labels.

Logs: only empty plant searches are sent. The search box searches as you type, so a miss is only counted when the
person settles on the term: they stop typing for 1.5 seconds, or sooner press Enter, switch to the Photo tab or close
the dialog (`recordSearchMiss`). The
server checks again that it finds nothing. One log line each, with the search term (lower-cased, trimmed, at most
100 characters) as `search_term`. The term is in Loki rather than Prometheus, because one series per term
would grow without limit. Grafana → Explore → Loki:
`{service_name="fernslop-backend"} | scope_name="fernslop.search"`.

## Alerts

Grafana → Alerting → Alert rules → **Fernslop**. They are provisioned from `grafana/provisioning/alerting/`. No
contact point is set up, so they show there and are not sent anywhere yet.

- **Plant search term keeps finding nothing** ([what it means](../docs/observability.md#alerting-on-user-impact)):
  more than 4 misses for one term in an hour, for 10 minutes. Checked every 5 minutes. A miss counts at most once per opening
  of the dialog, so this is several real searches for a plant the table does not have. Labels: `owner=product`,
  `severity=warning`, `service`, `environment`, `version`, `search_term`. The annotations hold a summary, the runbook and
  `dashboard_url`. That link is
  built from `GF_SERVER_ROOT_URL`, which locally is `http://localhost:3000` (`GRAFANA_ROOT_URL` to change).

## On a server

`infra/obs-deploy.sh` runs this same stack on its own EC2 instance, with `docker-compose.server.yaml` on top: Caddy
with HTTPS, a Grafana login and a token for OTLP. See [Observability server](../infra/README.md#observability-server).

## Files

- `otel-collector.yaml`: receivers, and the exporters to Tempo, Prometheus and Loki. Resource attributes become Prometheus labels
- `tempo.yaml`, `loki.yaml`, `prometheus.yml`: single-node configs with local storage
- `grafana/provisioning/datasources/`: the three data sources, linked so a trace opens its logs
- `grafana/dashboards/`: dashboards loaded at start-up (edits made in Grafana are not saved back here)
- `docker-compose.server.yaml`, `Caddyfile.server`: server only (above)
