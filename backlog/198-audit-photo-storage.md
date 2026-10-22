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
