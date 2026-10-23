# [env] CI: build on push to main, deploy to dev and verify

## Goal

Every push to `main` that passes the tests is built once by `infra/build.sh` (#235), deployed to dev with `infra/deploy.sh dev <tag>`, and proven live: dev's `/api/health` reports that tag (#229) and a read-only smoke test passes. Supersedes [#228](parked/228-ci-deploy-and-health-check.md).

## Acceptance criteria

- [ ] `.github/workflows/ci.yaml` gains jobs `build` and `deploy-dev` that run only when `github.event_name == 'push'` and `github.ref == 'refs/heads/main'` (skipped on PRs), `build` after `backend`, `frontend` and `stack`, `deploy-dev` after `build`. Neither job has `environment:`; only these two get `id-token: write`; the workflow's concurrency group stays as is, so `main` runs never overlap or cancel a running deploy
- [ ] `build` assumes `vars.AWS_DEPLOY_ROLE_ARN` in `vars.AWS_REGION`, runs `infra/build.sh` once (arm64, via SHA-pinned QEMU/buildx actions) and exposes its last stdout line as job output `tag`. No other step builds or pushes an image, and no job deploys `ecr-stack.yaml`
- [ ] `deploy-dev` fails with a one-line message, before deploying, if a needed variable is empty or the dev stack does not exist (CI never creates a stack). Otherwise it runs `infra/deploy.sh dev "$TAG"` with `CFN_ROLE_ARN` from `vars.AWS_CFN_ROLE_ARN`, the tag passed via `env:`, never `${{ }}` inside `run:`
- [ ] It then reads dev's `Url` stack output and polls `<Url>/api/health` (up to ~2 minutes) until it returns 200 with `version` equal to the tag; on timeout it fails, printing the expected tag and the last body. No rollback
- [ ] The smoke test only reads: `GET <Url>/` returns 200 HTML and `GET <Url>/api/plants` returns 200 with a non-empty JSON array. It sends no POST/PATCH/DELETE (dev holds a real-data copy, and write routes have per-IP limits)
- [ ] `build.sh` and `deploy.sh` use `AWS_REGION` when it is set (CI has no `aws configure` region), and pass `bash -n` and `shellcheck`. Every new action is pinned to a full commit SHA with a tag comment, and checkout keeps `persist-credentials: false`
- [ ] `actionlint` passes on the workflow. `infra/README.md` describes the CI flow and corrects the claim that nothing changes for the operator: once CI runs with `--role-arn`, CloudFormation keeps that role on the stack for later manual runs ([#233](parked/233-ci-deploy-iam-hardening.md) item 4)

## Out of scope

- Promoting to prod: [#239](239-env-ci-promote-to-prod.md). Rollback on a failed check: [#230](parked/230-ci-deploy-rollback.md)
- Making the checks required on `main`: [#231](parked/231-ci-required-status-checks.md). Scrubbing dev's real data: [#241](parked/241-env-dev-data-scrub.md)
- Deploying the `fernslop-ecr` stack (manual, [#235](235-env-build-and-deploy-by-tag.md)); role trust and rights ([#236](236-env-iam-split-per-environment.md))

## Constraints

- Starts after #229, #234, #235 and #236 are merged. Only `.github/workflows/ci.yaml`, `infra/README.md`, and the region lookup in `infra/build.sh`/`deploy.sh`
- Nobody but the user writes to AWS: check by reading the workflow, `actionlint` and `shellcheck` (brew or a container, not `pyproject.toml`). No tests
- A newer push may replace a queued (not running) `main` run, so not every commit reaches dev; that is fine. Re-running only the failed `deploy-dev` reuses `build`'s tag
