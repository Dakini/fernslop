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

## Comments

**Engineer:** Changed only `Dockerfile`, `backend/app/routers/health.py` and `backend/app/test_main.py`.

- Criterion 1: pass. `ARG FERNSLOP_IMAGE_TAG=""` plus `ENV FERNSLOP_IMAGE_TAG=$FERNSLOP_IMAGE_TAG` in the runtime stage; the route reads the env var per request. Built with `--build-arg FERNSLOP_IMAGE_TAG=20261023-120000-abc1234`, run with SQLite: `curl /api/health` gave `200 {"status":"ok","version":"20261023-120000-abc1234"}`.
- Criterion 2: pass. Built with no arg and with `--build-arg FERNSLOP_IMAGE_TAG=`: both gave `200 {"status":"ok"}`. The route strips the value and leaves `version` out when it is blank.
- Criterion 3: pass. `version` is the env var's value only, nothing else is added.
- Criterion 4: pass. The 503 branch is untouched; `test_health_returns_503_when_the_database_is_unreachable` still passes.
- Criterion 5: pass. The `ARG` sits after every `RUN` and `COPY` (just before `CMD`, after `EXPOSE`), so it is later than the issue asked: with `--progress=plain`, a build that changed only the tag showed every step `CACHED`, `useradd` included.
- Criterion 6: pass. Two tests in `backend/app/test_main.py`: `test_health_returns_ok` now unsets the env var and still expects exactly `{"status": "ok"}` (name kept because `_docs/testing-guidelines.md` cites it), and `test_health_with_an_image_tag_returns_it_as_version` is new.
- The route keeps `include_in_schema=False`; the field is documented in its docstring. No deploy file sets the variable (infra/ not touched).

Tests: `cd backend && uv run pytest` 184 passed, 2 skipped; `uvx ruff check .` clean.

**QA:**

## QA: PASS

- [x] Build with `--build-arg FERNSLOP_IMAGE_TAG=20261023-120000-abc1234`, run, `curl /api/health` returns `200 {"status": "ok", "version": "20261023-120000-abc1234"}` - PASS
      Built and ran the image with SQLite; got exactly that body and a 200.
- [x] Built without the arg (or empty) returns exactly `{"status": "ok"}` - PASS
      Built with no arg and with `--build-arg FERNSLOP_IMAGE_TAG=`; both returned `200 {"status":"ok"}`.
- [x] `version` holds only the tag string - PASS
      `health.py` adds only the stripped env var value; no SHA, time, hostname or env name.
- [x] The 503 "database is not answering" response is unchanged - PASS
      503 branch untouched in `health.py`; `test_health_returns_503_when_the_database_is_unreachable` passes.
- [x] Changing only the tag reuses the cached dependency and frontend layers - PASS
      Rebuilt with a different tag: every RUN and COPY step (npm ci, frontend build, uv sync, useradd) showed CACHED. The `ARG` sits after all of them.
- [x] Backend tests cover tag set and tag unset (at most 2, in `backend/app/test_main.py`) - PASS
      `test_health_returns_ok` (tag unset) and `test_health_with_an_image_tag_returns_it_as_version`; no more than 2 added or changed.

Scope: `FERNSLOP_IMAGE_TAG` appears only in `Dockerfile`, `health.py` and `test_main.py`; no deploy file sets it; the route keeps `include_in_schema=False`.

Tests: `cd backend && uv run pytest`, 184 passed, 2 skipped, 0 failed
