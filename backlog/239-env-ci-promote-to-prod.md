# [env] CI: manual workflow that promotes dev's image to prod

## Goal

A workflow started by hand, `.github/workflows/promote.yaml`, deploys to prod the exact image tag dev runs, without building, and proves prod's `/api/health` now reports that tag.

## Acceptance criteria

- [ ] Trigger is `workflow_dispatch` only, with no inputs. One job with `environment: production`, `permissions` `contents: read` and `id-token: write`, `concurrency` group `promote-prod` with `cancel-in-progress: false`, and a `timeout-minutes`. Its first step fails with a one-line message unless `github.ref` is `refs/heads/main`, before any AWS step
- [ ] It assumes `vars.AWS_DEPLOY_ROLE_ARN` in `vars.AWS_REGION` (the `production` environment's values, #236), gets both stack names from `infra/deploy.sh <env> --names` (#234), and reads the tag from SSM `/<dev stack>/deployed-tag`. A missing parameter, or a value not in `YYYYMMDD-HHMMSS-shortsha` format, stops the run
- [ ] Before any prod change it calls `$DEV_SITE_URL/api/health` (a repo variable: the prod role cannot read dev's stack outputs). Unless it gets `200` with `status` `ok` and `version` equal to the tag within a few retries, the run stops and prints the expected and actual values. An unset `DEV_SITE_URL` stops it too
- [ ] It stops if the prod stack does not exist (CI never creates prod, #237). If prod's own `deployed-tag` already equals the tag, it skips the deploy and only runs the prod check below
- [ ] Otherwise it runs `infra/deploy.sh prod <tag>` with `CFN_ROLE_ARN` from `vars.AWS_CFN_ROLE_ARN`, then calls prod's `/api/health` (stack output `Url`) and passes only on `200` with `version` equal to the tag. The tag and the result go to `$GITHUB_STEP_SUMMARY`
- [ ] The file has no `docker build`, `buildx`, `build.sh`, ECR login or push. Actions are pinned to full SHAs with a version comment as in `ci.yaml`, and `actionlint` (which runs `shellcheck` on `run:` blocks) reports nothing
- [ ] `infra/README.md` gets a short "Promote to prod" section: how to start it (Actions tab, or `gh workflow run promote.yaml --ref main`), setting `DEV_SITE_URL`, and limiting the `production` environment's deployment branches to `main`, since the prod role trusts the environment, not the branch

## Out of scope

- Rolling back when prod's check fails: [#230](parked/230-ci-deploy-rollback.md). Until then a red run leaves prod as `deploy.sh` left it
- Schema migrations: [#140](parked/140-db-migrations.md); every tag is promoted the same way
- Build and dev deploy: [#238](238-env-ci-build-and-deploy-dev.md). `version` in health: [#229](229-ci-deploy-version-check.md). Roles and environment variables: [#236](236-env-iam-split-per-environment.md). `deploy.sh prod <tag>`, `prod-<tag>` and recording the tag: [#235](235-env-build-and-deploy-by-tag.md). Creating prod: [#237](237-env-prod-stack-and-cutover.md)

## Constraints

- Only `.github/workflows/promote.yaml` (new) and that README section; not `ci.yaml`, which #238 owns. Use the same `configure-aws-credentials` pin as #238
- Starts after #229, #234, #235 and #236; the first live run is after #237
- Decided: no approval gate beyond starting the run by hand, so no required reviewers and no confirm input
- Agents never write to AWS or start the workflow. QA checks by reading the file and running `actionlint` (brew or the `rhysd/actionlint` image, not `pyproject.toml`)
