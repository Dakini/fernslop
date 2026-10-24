# Fernslop

A shared garden planner. People create a garden, search for plants or identify them from a photo, and place them on a map of the garden, next to areas such as ponds or veg beds.

## The problem

Gardeners keep track of their plants in their heads, on paper or in photos. It is hard to remember what is planted where, when each plant needs watering or feeding, and to share that with the people who help look after the garden.

Fernslop gives each real garden one shared, living plan. Anyone with the link can see it, add to it and keep it tended. There are no accounts to create.

## What it does

- **Gardens.** Anyone can create a garden (a home garden, allotment or balcony). All gardens are listed on the home page and can be shared by link.
- **Plant search.** Search a table of about 50 common garden plants by common or scientific name.
- **Photo identification.** Upload a photo of a plant. The app suggests up to 3 matches with a confidence score, and the user picks the right one. If none fits, they search instead.
- **Garden canvas.** Plants appear as round tokens on a map of the garden. Drag them to where they are planted. Add labelled areas, such as "Pond" or "Veg bed", and move, resize, rename or delete them.
- **Care rings.** Each plant shows a countdown for watering, feeding, pruning and harvesting, based on that plant's data. Marking a task done resets its ring.
- **Activity feed.** Every change (plant added, moved, watered, removed) shows in the garden's feed. Most changes can be undone from there. People can also post a message and a photo.
- **Live updates.** Changes made by one visitor show up for everyone else on the page without reloading.
- **Nicknames.** Each device gets a fun default name ("Anonymous Hedgehog"), which the user can change. The feed shows who did what.
- **Follow by email.** Visitors can follow a garden with their email. They confirm it first, and get a weekly summary when the garden had activity. Every email has an unsubscribe link.
- **Delete a garden.** A deleted garden is hidden at once and removed for good after 7 days.

## Expected behaviour

| When the user... | The app... |
| --- | --- |
| Creates a garden | Opens it and offers a link to share |
| Searches for a plant | Lists matching plants with image and names; the user picks one before it is added |
| Uploads a photo to identify | Accepts JPG, PNG or WebP up to 5 MB, and shows up to 3 candidates to confirm |
| Adds a plant | Places it in the middle of the canvas, ready to drag, and posts it to the feed |
| Drags a plant or area | Saves the position (as a percentage, so it scales to any screen) and shows it live to others |
| Marks a plant watered | Resets the water ring and posts to the feed |
| Clicks Undo on a feed event | Reverts that change |
| Adds a 51st plant or 11th area | Shows "This garden is full" and adds nothing |
| Goes too fast (e.g. many uploads) | Shows "You're going a bit fast. Try again in N seconds." |
| Searches for a plant that is not in the table | Records the miss; a repeated miss raises an alert (see On-call engineer) |
| Opens a page that does not exist | Shows a "Page not found" page with a link home |

The app works on phones and desktops. Every canvas action can also be done from the plant list, without dragging.

## How it is built

```
Browser (React SPA) --/api--> FastAPI backend --> PostgreSQL (SQLite for local dev)
                                     |
                                     +--> Pl@ntNet (photo identification, optional)
                                     +--> OpenTelemetry --> Grafana stack
```

| Part | Folder | Stack |
| --- | --- | --- |
| Frontend | `frontend/` | React 19, TanStack Router and Query, Tailwind, Vite. A mock service lets it run without a backend. |
| Backend | `backend/` | Python 3.12, FastAPI, SQLAlchemy, Pillow for photo checks. API in `openapi.yaml`. |
| Database | | PostgreSQL in Docker and in the cloud, SQLite when run on its own |
| Live updates | `backend/app/live.py` | Server-Sent Events per garden |
| Observability | `observability/` | OpenTelemetry Collector, Tempo, Prometheus, Loki, Grafana |
| Infrastructure | `infra/` | AWS CloudFormation: one EC2 server per environment, ECR, GitHub OIDC |
| CI/CD | `.github/workflows/` | Tests, build and deploy to dev on push to `main`; prod promoted by hand |
| On-call engineer | `on-call-engineer/` | A script that hands Grafana alerts to a coding agent |

One Docker image holds both parts: the backend serves the built frontend and the API on the same origin.

## Run it locally

You need [uv](https://docs.astral.sh/uv/), Node.js 24 and Docker.

**Whole stack in Docker** (Postgres, app, and the observability stack):

```sh
make up       # app on http://localhost:8000, Grafana on http://localhost:3000
make down     # stop, keep data
make delete   # stop and delete the app's database
```

**Backend and frontend separately**, for development:

```sh
make install       # backend dependencies
make backend-dev   # API on http://localhost:8091, reloads on change
cd frontend && npm install && npm run dev   # proxies /api to the backend
```

API docs are at `/api/docs` while the backend runs. To run the frontend with no backend, set `VITE_USE_MOCK=true` in `frontend/.env.local`.

### Settings

All optional. The defaults work for local use.

| Variable | Default | What it does |
| --- | --- | --- |
| `FERNSLOP_DATABASE_URL` | `sqlite:///fernslop.db` | Database to use |
| `FERNSLOP_IDENTIFY_PROVIDER` | stub | Set to `plantnet` for real photo identification |
| `FERNSLOP_IDENTIFY_API_KEY` | | Pl@ntNet API key |
| `FERNSLOP_PUBLIC_URL` | | Site address used in email links |
| `FERNSLOP_API_DOCS` | `1` | `0` hides the API docs (prod) |
| `FERNSLOP_RATE_LIMIT_*` | see `backend/app/rate_limit.py` | Per-action rate limits |

Without a Pl@ntNet key, photo identification returns stub matches, so the flow can still be tried.

### Scheduled jobs

Run from `backend/`:

```sh
uv run python -m app.digest       # weekly email digest to followers
uv run python -m app.room_purge   # remove gardens deleted over 7 days ago
```

## Tests

```sh
make test            # backend (pytest)
make test-frontend   # frontend (Vitest)
make test-e2e        # browser tests (Playwright) against a throwaway Docker stack
make test-all        # all three
```

The end-to-end tests check the main journeys with two browsers at once: sharing a garden and seeing a plant move live, posting a photo, and the "Page not found" page. See `e2e/README.md` and `_docs/testing-guidelines.md`.

CI runs all of these on every push.

## Deploy

A push to `main` runs the tests, builds the image, pushes it to ECR and deploys it to the dev server. The "Promote to prod" workflow deploys the same image to prod. Setup steps are in `infra/README.md`.

## Observability and on-call

The app sends traces, metrics and logs to Grafana (`observability/README.md`). Grafana has a dashboard and an alert for a plant search term that keeps finding nothing.

`on-call-engineer/oncall.py` polls Grafana's alerts every minute. Each new alert goes to a headless coding agent in its own git worktree. If a code change fixes it (for example, adding the missing plant to the seed table), the script commits it to a branch for review. If a person must act, it files a GitHub issue labelled `on-call`. See `on-call-engineer/README.md`.

## How the work was done

The work was planned as small issues in `backlog/` (`done/` for finished, `parked/` for later). Each issue was groomed, built and checked against its acceptance criteria by separate roles (PM, engineer, QA). The process is in `_docs/process.md` and `_docs/team/`.

Other docs:

- `_docs/plan.md`: the first MVP plan
- `_docs/lovable-spec.md`: the product spec the app follows
- `_docs/design-system.md`: colours, type and components
- `audit.md`: a review of the app, which led to the `audit-*` issues

## Not done yet

- Emails are printed to the console, not sent (`backlog/parked/110-api-email-sender.md`).
- Live updates work with one backend process only (`090-api-live-multi-worker.md`).
- There are no database migrations yet (`140-db-migrations.md`).
- Other planned work is in `backlog/parked/`.
- There are no accounts or private gardens, by design: anyone with the link can edit. The feed and Undo are the safeguard.
