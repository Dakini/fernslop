# Getting started

Set up Fernslop on your machine, run it, and run the tests. To deploy it to AWS, see [`deployment.md`](deployment.md).

## Prerequisites

| Tool | Version | Used for |
| --- | --- | --- |
| [Docker](https://docs.docker.com/get-docker/) with Compose v2 | recent | Running the full stack |
| [uv](https://docs.astral.sh/uv/) | recent | Python 3.12+ and backend dependencies |
| [Node.js](https://nodejs.org/) | 24 | Frontend |
| `make` | any | The commands below |

Developed on macOS; CI runs on Linux. On Windows, use WSL 2.

## 1. Clone

```sh
git clone https://github.com/Dakini/fernslop.git
cd fernslop
```

## 2. Run the full stack (one command)

```sh
make up
```

This builds the image and starts:

| Service | Address | What it is |
| --- | --- | --- |
| App | http://localhost:8000 | Frontend and API (`/api`), served by one container |
| Postgres | inside Docker | The database, in the `pgdata` volume |
| Grafana | http://localhost:3000 | Traces, metrics, logs and alerts |

It waits until everything is healthy. Then open http://localhost:8000. Three demo gardens are seeded, so there is something to look at straight away.

Check the backend:

```sh
curl http://localhost:8000/api/health
# {"status":"ok","version":"local-<git sha>"}
```

Stop it:

```sh
make down     # stop, keep the data
make delete   # stop and delete the app's database
```

Use another port with `make up APP_PORT=8080`.

## 3. Run for development

The backend and frontend run on their own, with reload on change. The backend uses a SQLite file, so Docker is not needed.

```sh
make install       # backend dependencies (uv sync)
make backend-dev   # API on http://localhost:8091
```

In a second terminal:

```sh
cd frontend
npm install
npm run dev        # prints its URL; /api is proxied to :8091
```

API docs (Swagger UI) are at http://localhost:8091/api/docs. The contract is [`openapi.yaml`](../openapi.yaml).

To work on the frontend with no backend at all, put `VITE_USE_MOCK=true` in `frontend/.env.local`. An in-browser mock then stands in for the API.

## 4. Run the tests

```sh
make test-all
```

| Command | Suite | What it covers |
| --- | --- | --- |
| `make test` | Backend, pytest | Unit tests, and integration tests of every API route against a real database |
| `make test-frontend` | Frontend, Vitest | Components, the services layer, identity and helpers |
| `make test-e2e` | End to end, Playwright | Real browsers against a throwaway copy of the Docker stack |

The first time, install the browser for the end-to-end tests: `cd e2e && uv run playwright install chromium`. How that suite runs, and its options, are in [`e2e/README.md`](../e2e/README.md).

The backend tests use SQLite by default. To run them against Postgres too, set `FERNSLOP_TEST_DATABASE_URL`. Otherwise the 2 Postgres-only tests are skipped.

## 5. Configuration

Everything is optional. The defaults work for local use.

| Variable | Default | What it does |
| --- | --- | --- |
| `FERNSLOP_DATABASE_URL` | `sqlite:///fernslop.db` | Database. `make up` points it at Postgres |
| `FERNSLOP_IDENTIFY_PROVIDER` | stub | `plantnet` for real photo identification |
| `FERNSLOP_IDENTIFY_API_KEY` | | [Pl@ntNet](https://my.plantnet.org/) API key |
| `FERNSLOP_PUBLIC_URL` | | Site address used in email links |
| `FERNSLOP_ENVIRONMENT` | `local` | `dev` or `prod` on the servers; added to telemetry |
| `FERNSLOP_API_DOCS` | `1` | `0` hides the API docs |
| `FERNSLOP_RATE_LIMIT_*` | see [`rate_limit.py`](../backend/app/rate_limit.py) | Per-action limits, e.g. `10/hour` |
| `OTEL_*_EXPORTER` | `none` | `otlp` sends telemetry. `make up` sets it |

Without a Pl@ntNet key, photo identification returns stub matches, so the whole flow can still be tried.

## 6. Scheduled jobs

These run on the servers. Locally, run them by hand from `backend/`:

```sh
uv run python -m app.digest          # weekly email to followers (printed, not sent; see below)
uv run python -m app.room_purge      # remove gardens deleted over 7 days ago, and unconfirmed follows
uv run python -m app.photo_cleanup   # remove uploaded photos never posted
```

Emails are printed to the console for now. A real sender is planned in `backlog/parked/110-api-email-sender.md`.

## Troubleshooting

| Problem | Fix |
| --- | --- |
| `make up` says the port is in use | `make up APP_PORT=8080`, or stop whatever uses port 8000 or 3000 |
| Frontend shows network errors in dev | Start the backend with `make backend-dev` first, or use `VITE_USE_MOCK=true` |
| e2e tests fail with "Executable doesn't exist" | `cd e2e && uv run playwright install chromium` |
| You want a clean database | `make delete && make up` |
| Nothing shows in Grafana | Telemetry is exported every minute. Wait a minute, or check `make up` started the observability stack |
