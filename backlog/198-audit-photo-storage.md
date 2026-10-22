# [audit] Stop unposted photos from filling the disk

## Goal

On the deployed stack, unposted photos are cleaned up and soft-deleted gardens purged automatically, and photo uploads stop with a clear message before photos can fill the 20 GB disk (`audit.md` 2, second and third bullets). `POST /api/plants/identify` stores nothing and is not affected.

## Acceptance criteria

- [ ] `python -m app.photo_cleanup` defaults to photos older than 6 hours instead of 24 (a post written slowly within 6 hours keeps its photo); `--hours` still overrides.
- [ ] `infra/ec2-stack.yaml` installs systemd timers (`Persistent=true`) that run, through `docker compose run --rm app` so the output lands in the CloudWatch log group, `app.photo_cleanup` hourly and `app.room_purge` from #196 daily.
- [ ] `POST /api/photos` answers 507 with message `Photo storage is full right now. Please try again later.` and stores nothing when the stored photo bytes are at or above `FERNSLOP_PHOTO_STORAGE_LIMIT_BYTES` (default 4 GiB); below it uploads work as before. The toast shows that message.
- [ ] The total comes from one aggregate query that does not load photo bytes into Python (e.g. `SUM` of the byte length), on both SQLite and Postgres.
- [ ] `openapi.yaml` `uploadPhoto` documents the 507 and the env variable; the mock service never reports full.
- [ ] Tests: at the ceiling gives 507 and stores nothing; the cleanup default is 6 hours.

## Out of scope

- The Caddy body limit that stops oversize uploads at the edge: [#203](203-audit-edge-hardening.md).
- Per-IP upload limits: [#195](195-audit-rate-limit.md).
- Object storage for photos: [parked #205](parked/205-audit-photo-object-storage.md).
- Getting the timers onto an already running instance: [#208](208-audit-apply-to-running-instance.md).

## Constraints

- `backend/app/photo_cleanup.py`, `routers/photos.py`, `sql_store.py` (and `store.py` if the method joins the protocol), `openapi.yaml`, `infra/ec2-stack.yaml`.
- After #196 (`app.room_purge`). Parallel uploads may overshoot the ceiling by a few photos: accepted.
- At most 3 tests.

## Comments

**Engineer:** Implemented on branch `worktree-agent-af8c5b6dbbc97ddea`.
- `app/photo_cleanup.py`: default `--hours` is now 6 (`DEFAULT_HOURS`); `--hours` still overrides.
- `sql_store.py` / `store.py`: new protocol method `photo_storage_bytes()`, one `SELECT COALESCE(SUM(LENGTH(data)), 0)` (byte length of the BLOB/bytea on SQLite and Postgres, no photo loaded into Python).
- `routers/photos.py`: `upload_photo` checks the total first (3 lines at the top of the function) and raises `ApiError(507, "Photo storage is full right now. Please try again later.")` when it is at or above `FERNSLOP_PHOTO_STORAGE_LIMIT_BYTES` (default 4 GiB). The existing upload toast already shows the server's `message`, so no frontend change; the mock's `uploadPhoto` never reports full.
- `infra/ec2-stack.yaml`: user-data writes `fernslop-task@.service` (oneshot, `docker compose run --rm -T app python -m app.%i` in `/opt/app`, so output goes to the awslogs CloudWatch group) and two timers with `Persistent=true`: `fernslop-photo-cleanup.timer` (hourly, `photo_cleanup`) and `fernslop-room-purge.timer` (daily, `room_purge`), then enables them. Only additions after `docker compose up`, no other lines changed. Not deployed.
- `openapi.yaml`: `uploadPhoto` documents the 507, the env variable, the 6-hour cleanup and that the mock never reports full.
- Tests (2): `test_upload_once_stored_photo_bytes_reach_the_limit_is_507_and_stores_nothing` (one upload below the ceiling succeeds, the next is 507 with the message and stores nothing); the cleanup test now runs with the default and checks a 7-hour orphan goes while a 5-hour one stays.
- Results: `uv run pytest` 152 passed, 2 skipped; the photo and cleanup tests also pass on Postgres 17 (`FERNSLOP_TEST_DATABASE_URL`, 15 passed); `uvx ruff check .` clean; `cfn-lint infra/ec2-stack.yaml` clean.
