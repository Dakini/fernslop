# [env] CI: build on push to main, deploy to dev and verify

## Goal

Every push to `main` that passes the tests is built once by `infra/build.sh` and pushed to ECR, deployed to dev through the SSM document ([#236](236-env-iam-split-per-environment.md)), and proven live: dev's `/api/health` reports that tag ([#229](done/229-ci-deploy-version-check.md)). The `deployed-dev` git tag then marks what dev runs. Supersedes [#228](parked/228-ci-deploy-and-health-check.md).

## Acceptance criteria

- [ ] `.github/workflows/ci.yaml` gains `build-and-push`, then `deploy-dev`, both only when `github.event_name == 'push'` and `github.ref == 'refs/heads/main'`. `build-and-push` needs `backend`, `frontend` and `stack`; `deploy-dev` needs `build-and-push`. The existing concurrency group stays, so `main` runs never overlap
- [ ] `build-and-push` (`id-token: write`, no `environment:`) assumes the push role from repo variable `ECR_PUSH_ROLE_ARN` in `vars.AWS_REGION`, then runs `infra/build.sh` once (arm64, SHA-pinned QEMU/buildx) and outputs its last stdout line as `tag`. Nothing else builds or pushes, and no CI job calls CloudFormation or `deploy.sh`
- [ ] `deploy-dev` has `environment: development`, `id-token: write` and `contents: write` (this job only), and assumes `vars.AWS_DEPLOY_ROLE_ARN`. It first fails with a one-line message if any of `AWS_DEPLOY_ROLE_ARN`, `AWS_REGION`, `INSTANCE_ID`, `DEPLOY_DOCUMENT`, `PUBLIC_URL` is empty. The tag goes in via `env:`, never `${{ }}` inside `run:`
- [ ] It sends `DEPLOY_DOCUMENT` to `INSTANCE_ID` with parameter `tag` via `ssm send-command` (never CloudFormation or `AWS-RunShellScript`), waits, and fails with the command's stdout and stderr unless the status is `Success`
- [ ] It polls `$PUBLIC_URL/api/health` (up to ~2 minutes) until 200 with `version` equal to the tag. On timeout it fails and prints the expected tag and the last body. No rollback
- [ ] Read-only smoke test: `GET /` returns 200 HTML and `GET /api/plants` returns 200 with a non-empty JSON array. No POST/PATCH/DELETE (dev holds a real-data copy, and write routes have per-IP limits). Only then does it run `git tag -f deployed-dev` and `git push -f origin deployed-dev`; a failed deploy, health check or smoke test leaves the tag alone
- [ ] Actions are pinned to a full commit SHA with a tag comment, checkout keeps `persist-credentials: false` (the push uses the job token), and `actionlint` passes. `infra/README.md` describes this flow, the variables above (repo level: push role, region; `development` environment: the rest) and that rerunning only a failed `deploy-dev` reuses `build-and-push`'s tag

## Out of scope

- Promoting to prod: [#239](239-env-ci-promote-to-prod.md). Rollback on a failed check: [#230](parked/230-ci-deploy-rollback.md)
- Making the checks required on `main`: [#231](parked/231-ci-required-status-checks.md). Scrubbing dev's real data: [#241](parked/241-env-dev-data-scrub.md)
- `build.sh`, the SSM document, the ECR stack and the push/deploy roles: [#235](235-env-build-and-deploy-by-tag.md), [#236](236-env-iam-split-per-environment.md). Applying them live is the user's

## Constraints

- Starts after #229, #234, #235 and #236 are merged. Only `.github/workflows/ci.yaml` and `infra/README.md`. The workflow never creates a stack, so a first deploy stays manual
- Nobody but the user writes to AWS: check by reading the workflow and running `actionlint` (brew or a container, not `pyproject.toml`). No tests
- A newer push may replace a queued (not running) `main` run, so not every commit reaches dev; that is fine
