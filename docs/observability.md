# Observability, alerts and on-call

How Fernslop reports what it is doing, how it raises an alert when users are affected, and how an on-call agent responds.

Detailed references: [`observability/README.md`](../observability/README.md) and [`on-call-engineer/README.md`](../on-call-engineer/README.md).

## Signals

The backend uses the OpenTelemetry SDK (`backend/app/telemetry.py`). It sends three signals to an OpenTelemetry Collector, which stores each one and makes it viewable in Grafana:

```
backend ──OTLP──▶ Collector ──traces──▶ Tempo       ┐
                            ──metrics─▶ Prometheus  ├──▶ Grafana (dashboards, Explore, alerts)
                            ──logs────▶ Loki        ┘
```

| Signal | What is recorded | Where to look |
| --- | --- | --- |
| Traces | One server span per HTTP request | Grafana → Explore → Tempo, `service.name = fernslop-backend` |
| Metrics | Gardens created, plants added, failed creates (by reason), photos uploaded, active participants, empty plant searches | Grafana → Dashboards → **Fernslop app metrics** |
| Logs | Structured log records for empty plant searches, with the request's `trace_id` and `span_id` | Grafana → Explore → Loki, `{service_name="fernslop-backend"}` |

Every signal carries the same resource: `service.name`, `deployment.environment.name` (`local`, `dev` or `prod`) and `service.version` (the image tag). The dashboard filters on environment and version.

## Key user journey: finding a plant

The instrumented journey is **adding a plant by search**. It is the core of the app, and a failed search means a user can't add their plant.

1. The user types into **Add a plant**. Each search is a `GET /api/plants/search` request, with its own trace.
2. If the search the user settles on finds nothing, the frontend reports it (`POST /api/plants/search/misses`).
3. The backend checks again that it finds nothing, then:
   - adds 1 to the `fernslop.plant_search.empty` metric
   - writes a structured log record on the `fernslop.search` logger, with the term as `search_term`
4. The log record carries the trace ID of that request. In Grafana, a log line links to its trace in Tempo, and a trace links to its logs.

So the metric, the trace and the log of one search can be followed together.

## Privacy: what is not sent

- Request and response bodies and headers are never recorded. That rules out emails, photos, device IDs and nicknames.
- The only user text sent is the empty search term: lower-cased, trimmed and capped at 100 characters. It goes to logs, not to metric labels.
- No credentials or tokens are sent. On the servers, the Collector only accepts telemetry with a bearer token, and Grafana needs a login.

## Alerting on user impact

Alerts are provisioned from `observability/grafana/provisioning/alerting/`.

| Alert | Fires when | Why it matters | Runbook |
| --- | --- | --- | --- |
| **Plant search term keeps finding nothing** | One search term found no plants more than 4 times in an hour, in one environment and version, for 10 minutes | Several people want a plant the table doesn't have, so they can't add it to their garden | Real plant: add it to `_PLANTS` in `backend/app/seed.py`. Typo or noise: silence the term for a week |

The alert's labels include `owner=product`, `severity=warning`, environment, version and `search_term`. The annotations include a summary, the runbook and a dashboard link.

## On-call agent

`on-call-engineer/oncall.py` polls Grafana's alerts every minute. For each new firing alert:

1. It creates a git worktree on a new branch, `oncall/<fingerprint>-<time>`. Your own checkout is not touched.
2. It starts a headless coding agent in that worktree, with the alert as data, and tells it to follow the runbook.
3. The agent investigates. If a code change fixes the alert, it makes the change and runs the backend tests. For example, it adds a missing plant to the seed table.
4. The script commits the agent's changes to the branch, ready to review and merge.
5. If a person must act, such as merging or silencing the alert, the agent drafts a GitHub issue. The script files it with the label `on-call`.
6. A report of each run is written to `on-call-engineer/reports/`.

```sh
uv run --script on-call-engineer/oncall.py           # poll every minute until Ctrl-C
uv run --script on-call-engineer/oncall.py --once    # poll once
```

The agent is sandboxed. It can only read and edit files in its worktree and run the tests. It cannot commit, push, use the network or run other commands. Alert text can contain whatever the public typed, so it is treated as data, never as instructions.

## Try it locally

```sh
make up                      # app, plus the observability stack
# open http://localhost:8000, open a garden, and search "Add a plant" for something
# not in the table (e.g. "wisteria") 5 times, closing the dialog in between
# Grafana: http://localhost:3000 → Alerting → Alert rules → Fernslop
uv run --script on-call-engineer/oncall.py --once
```

The alert must hold for 10 minutes and is checked every 5, so it takes about 15 minutes to fire.
