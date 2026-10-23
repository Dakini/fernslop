# [env] CI: manual workflow that promotes dev's image to prod

## Goal

A workflow started by hand deploys to prod the exact image that dev runs, without building, and proves prod's `/api/health` now reports that tag. It is `.github/workflows/promote.yaml`; `promote.yml` in `real-time-design` is the model.

## Acceptance criteria

- [ ] Trigger is `workflow_dispatch` only, no inputs. One job with `environment: production`, `contents: read` and `id-token: write`, `concurrency` group `promote-prod` (`cancel-in-progress: false`), and a `timeout-minutes`. Its first step fails with a one-line message unless `github.ref` is `refs/heads/main`, before checkout and AWS
- [ ] It checks out the git tag `deployed-dev` (`fetch-depth: 1`, `persist-credentials: false`) and stops with a clear message if the tag does not exist. It computes the image tag with `infra/build.sh --print-tag` (#235) on that commit and stops unless it matches `^[0-9]{8}-[0-9]{6}-[0-9a-f]{7}$`
- [ ] It assumes `vars.AWS_DEPLOY_ROLE_ARN` in `vars.AWS_REGION` (the `production` environment's values) with `configure-aws-credentials`, the same SHA pin as #238. It stops before any AWS call if `AWS_DEPLOY_ROLE_ARN`, `AWS_REGION`, `INSTANCE_ID`, `DEPLOY_DOCUMENT` or `PUBLIC_URL` is empty
- [ ] It runs `aws ssm send-command` with `--document-name "$DEPLOY_DOCUMENT"` on `$INSTANCE_ID` and parameter `tag`, passed via `env:`, never `${{ }}` inside `run:`. It waits for the invocation, prints its stdout, and fails with stderr unless the status is `Success`. It uses no `AWS-RunShellScript`, CloudFormation, ECR, S3 or `deploy.sh`
- [ ] It then polls `$PUBLIC_URL/api/health` (up to ~2 minutes) and passes only on `200` with `status` `ok` and `version` equal to the tag. On timeout it fails, printing the expected tag and the last body. No rollback. The tag and result go to `$GITHUB_STEP_SUMMARY`
- [ ] The file has no `docker build`, `buildx`, `build.sh` build, ECR login or push. Actions are pinned to full SHAs with a version comment as in `ci.yaml`, and `actionlint` (with `shellcheck` on `run:` blocks) reports nothing
- [ ] `infra/README.md` gets a short "Promote to prod" section: start it from the Actions tab or `gh workflow run promote.yaml --ref main`, the five `production` environment variables, and limiting the `production` environment's deployment branches to `main`, since the prod role trusts the environment, not the branch

## Out of scope

- Rolling back when prod's check fails: [#230](parked/230-ci-deploy-rollback.md). Until then a red run leaves prod as the SSM document left it
- Schema migrations: [#140](parked/140-db-migrations.md); every tag is promoted the same way
- The `deployed-dev` tag, build and dev deploy: [#238](238-env-ci-build-and-deploy-dev.md). Tag format, `--print-tag` and the SSM document: [#235](235-env-build-and-deploy-by-tag.md). Roles and environments: [#236](236-env-iam-split-per-environment.md). `version` in health: [#229](229-ci-deploy-version-check.md). Creating prod: [#237](237-env-prod-stack-and-cutover.md)

## Constraints

- Only `.github/workflows/promote.yaml` (new) and that README section; not `ci.yaml`. Starts after #229, #234, #235, #236 and #238; the first live run is after #237
- Decided: no approval gate beyond starting the run by hand, so no required reviewers and no confirm input
- Agents never write to AWS or start the workflow. QA checks by reading the file and running `actionlint` (brew or the `rhysd/actionlint` image, not `pyproject.toml`)
