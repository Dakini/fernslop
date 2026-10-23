# [ci] Health check proves the newly deployed image is running

## Goal

An image built with a tag (format `YYYYMMDD-HHMMSS-shortsha`, from #235) reports that tag from `GET /api/health`, so the dev check (#238) and prod promotion (#239) can tell the new container from an old one.

## Acceptance criteria

- [ ] `docker build --build-arg FERNSLOP_IMAGE_TAG=20261023-120000-abc1234 .`, run, then `curl /api/health` returns `200 {"status": "ok", "version": "20261023-120000-abc1234"}`
- [ ] Built without the arg (or with it empty), `/api/health` returns exactly `{"status": "ok"}` as today, so local, compose and e2e runs are unchanged
- [ ] `version` holds only the tag string: no separate SHA, build time, hostname or env name (the endpoint is public)
- [ ] The 503 "database is not answering" response is unchanged
- [ ] Changing only the tag reuses the cached dependency and frontend layers (the `ARG` sits after `uv sync` and the frontend copy)
- [ ] Backend tests cover tag set and tag unset (at most 2 tests, in `backend/app/test_main.py`)

## Out of scope

- Passing `--build-arg FERNSLOP_IMAGE_TAG=<tag>` from the build script, #235
- Comparing the reported tag with the deployed one in CI, #238 (dev) and #239 (prod)
- Rollback when the tag does not match, [#230](parked/230-ci-deploy-rollback.md)

## Constraints

- Stay inside `Dockerfile`, `backend/app/routers/health.py` and `backend/app/test_main.py`
- The runtime stage turns the build arg into the env var `FERNSLOP_IMAGE_TAG`; the route reads it per request and omits `version` when it is unset or blank. Deploy files must not set it at run time
- The route stays out of `openapi.yaml` (`include_in_schema=False`); document the field in the route's docstring
- No new dependencies; follow `_docs/testing-guidelines.md`
