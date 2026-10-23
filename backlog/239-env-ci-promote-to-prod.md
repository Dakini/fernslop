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


## Engineer:

Added `.github/workflows/promote.yaml` and a "Promote to prod" section in `infra/README.md`. Nothing else changed (`ci.yaml` untouched). No tests: this is config.

- **Job:** `workflow_dispatch` only, no inputs. One job `promote` with `environment: production`, `id-token: write` + `contents: read`, `concurrency` group `promote-prod` (`cancel-in-progress: false`), `timeout-minutes: 45`. The five settings are job-level `env:`; the tag goes to later steps through `env:`, so no `${{ }}` appears inside a `run:`.
- **Steps, in order:** (1) fails with one line unless `$GITHUB_REF` is `refs/heads/main`, before checkout and AWS; (2) checks that the `deployed-dev` tag exists with `gh api repos/$GITHUB_REPOSITORY/git/ref/tags/deployed-dev` (the job token, `contents: read`) and stops with a message saying CI's `deploy-dev` creates it; (3) checkout of `refs/tags/deployed-dev` (`fetch-depth: 1`, `persist-credentials: false`); (4) `infra/build.sh --print-tag`, which must match `^[0-9]{8}-[0-9]{6}-[0-9a-f]{7}$`, written to a step output; (5) the settings check (any empty of `AWS_DEPLOY_ROLE_ARN`, `AWS_REGION`, `INSTANCE_ID`, `DEPLOY_DOCUMENT`, `PUBLIC_URL` fails with one line, before AWS); (6) `configure-aws-credentials` at the #238 pin `e1253824e5c10ff9df46874f81ed3ec929e19cfd` (v6.3.0); (7) `ssm send-command` of `$DEPLOY_DOCUMENT` on `$INSTANCE_ID` with `tag=$TAG`, polled like `deploy-dev` (10 s, up to 30 min), stdout always printed, stderr and exit 1 unless `Success`; (8) the health poll, 24 x 5 s, passes only on HTTP 200 with `.status == "ok" and .version == $TAG`; on timeout it prints the expected tag and the last body and exits 1. The tag and the result go to `$GITHUB_STEP_SUMMARY` on both outcomes. No rollback.
- **Not used:** no docker, buildx, `build.sh` build, ECR login/push, CloudFormation, S3, `deploy.sh` or `AWS-RunShellScript`. The only other action is `actions/checkout` at the existing `ci.yaml` pin.
- **README:** how to start it (Actions tab or `gh workflow run promote.yaml --ref main`), the five `production` environment variables in a table (`AWS_REGION` falls back to the repository value, as in the dev section), and the instruction to limit the `production` environment's deployment branches to `main` because the prod role trusts the environment, not the branch.
- **Checks:** `uvx --with shellcheck-py --from actionlint-py actionlint -verbose` (shellcheck on the `run:` blocks): 0 errors in both workflow files. Read the file against each criterion. Not run: the workflow, any AWS call or push.

Notes for QA / the PM:

- The criterion says "up to ~2 minutes" for the health poll and requires `status` `ok`; `deploy-dev` checks only `version`, this one checks both, as asked.
- The tag-existence check uses `gh api` (preinstalled on the runner) rather than a `git ls-remote`, because there is no checkout yet at that point and the repository may be private.
- `deployed-dev` is checked out by tag name at run time, so if a `main` push moves the tag between the existence check and checkout, the newer commit is promoted; that is the tag's current meaning, so I left it.
- The README's example prod document name is `prod-fernslop-deploy`, taken from the existing naming line at the top of the README.


## QA: PASS

Read `.github/workflows/promote.yaml` and `infra/README.md` against each criterion. The workflow was not run; no AWS or GitHub calls, no push, no code changed.

- [x] Trigger `workflow_dispatch` only, no inputs; one job with `environment: production`, `contents: read`, `id-token: write`, `concurrency` `promote-prod` (`cancel-in-progress: false`), `timeout-minutes: 45`; first step fails with one line unless `$GITHUB_REF` is `refs/heads/main`, before checkout and AWS - PASS
- [x] Checks out `refs/tags/deployed-dev` (`fetch-depth: 1`, `persist-credentials: false`); stops with a clear message if the tag is missing (`gh api .../git/ref/tags/deployed-dev`, run before checkout); tag from `infra/build.sh --print-tag`, rejected unless it matches `^[0-9]{8}-[0-9]{6}-[0-9a-f]{7}$`. `build.sh --print-tag` uses only `git show`/`rev-parse` on HEAD, so it works on a depth-1 checkout (locally it printed `20261023-192452-b4346b1`, which matches the regex) - PASS
- [x] `configure-aws-credentials` at `e1253824...` (v6.3.0), the same pin as `ci.yaml` (lines 174, 244), with `AWS_DEPLOY_ROLE_ARN` and `AWS_REGION` from the job env (the `production` environment's vars). The "Check the settings" step, before the AWS step, fails if any of the five variables is empty - PASS
- [x] `aws ssm send-command` with `--document-name "$DEPLOY_DOCUMENT"`, `--instance-ids "$INSTANCE_ID"`, `--parameters "tag=$TAG"`; values come from `env:`, and no `${{ }}` appears inside any `run:`. It polls the invocation, prints stdout, and prints stderr and exits 1 unless the status is `Success`. grep finds no `AWS-RunShellScript`, CloudFormation, ECR, S3 or `deploy.sh` - PASS
- [x] Health poll of `$PUBLIC_URL/api/health`, 24 x 5 s (~2 min), passes only on HTTP 200 with `.status == "ok" and .version == $TAG` (jq). On timeout it prints the expected tag and the last body and exits 1; no rollback. The tag and result go to `$GITHUB_STEP_SUMMARY` on both outcomes - PASS
- [x] No `docker build`, `buildx`, build, ECR login or push (grep of docker/buildx/ecr/cloudformation/s3/deploy.sh/RunShellScript matches only a comment). Both actions are pinned to full SHAs with version comments, the same as `ci.yaml`. actionlint with shellcheck reports 0 errors - PASS
- [x] `infra/README.md` has a "Promote to prod" section (line 246): start it from the Actions tab or `gh workflow run promote.yaml --ref main`; a table of the five `production` environment variables; and the instruction to limit the `production` environment's deployment branches to `main` because the prod role trusts the environment, not the branch - PASS

Constraints: only `promote.yaml` (new) and the README section were added, and `ci.yaml` is untouched (the only uncommitted change in the tree is `AGENTS.md`, which is not part of this issue).

Commands run:
- `uvx --with shellcheck-py --from actionlint-py actionlint -verbose` - Found 0 errors in 2 files (`promote.yaml`, `ci.yaml`)
- `infra/build.sh --print-tag` (local, read-only) - tag matches the regex
- `grep` for forbidden commands and for action pins in `promote.yaml` and `ci.yaml`

Tests: none apply (config only); the workflow itself needs a live run after #237.
