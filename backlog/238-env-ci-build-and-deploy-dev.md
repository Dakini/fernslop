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

## Engineer:

Changed only `.github/workflows/ci.yaml` and `infra/README.md` (new section "CI: build and deploy to dev"). No tests: this is config.

- **`build-and-push`:** `needs: [backend, frontend, stack]`, `if` push on `main`, `id-token: write` + `contents: read`, no `environment:`. Steps: checkout (`persist-credentials: false`), `configure-aws-credentials` with `vars.ECR_PUSH_ROLE_ARN` / `vars.AWS_REGION`, QEMU (arm64), buildx, then `infra/build.sh`. It takes the last stdout line as `tag`, checks it against the tag pattern and exposes it as the job output. `ECR_REPOSITORY_URI` is passed from the optional repo variable (build.sh falls back to the account lookup if it is empty).
- **`deploy-dev`:** `needs: [build-and-push]`, same `if`, `environment: development`, `id-token: write` + `contents: write`. The tag and the five settings are job-level `env:`, so no `${{ }}` appears inside a `run:`. Step 1 fails with one line listing any empty one of `AWS_DEPLOY_ROLE_ARN`, `AWS_REGION`, `INSTANCE_ID`, `DEPLOY_DOCUMENT`, `PUBLIC_URL` (and a bad tag), before checkout and AWS. Then: `ssm send-command` of `DEPLOY_DOCUMENT` with `tag=$TAG`, polled with `get-command-invocation` every 10 s for up to 30 min (`aws ssm wait` stops at 100 s), stdout always printed, stderr and exit 1 unless `Success`. Then the health poll (24 x 5 s, 200 and `.version == $TAG`; on timeout it prints the expected tag and the last body). Then the read-only smoke test (`GET /` 200 with a `text/html` content type; `GET /api/plants` 200 and a non-empty array). Only then `git tag -f deployed-dev` and a forced push over HTTPS with the job token in `GITHUB_TOKEN` (checkout stores no credentials). A failure in any earlier step skips the tag. No rollback.
- **Pins** (resolved with `gh api repos/<owner>/<repo>/commits/<tag> --jq .sha`; the tags are lightweight, so these are commit SHAs):
  - `aws-actions/configure-aws-credentials` `e1253824e5c10ff9df46874f81ed3ec929e19cfd` = `v6.3.0` (latest release). **This is the shared pin; #239's `promote.yaml` must use the same one.**
  - `docker/setup-qemu-action` `99012661954931238ded8c8b007157a8430204e1` = `v4.4.0`
  - `docker/setup-buildx-action` `f87e5991a6d7451dcb8d9637bfbc97413f497069` = `v4.4.1`
  - `actions/checkout` is unchanged (`3d3c42e5...` = `v7.0.1`).
- **README:** the flow, the variable table (repo: `ECR_PUSH_ROLE_ARN`, `AWS_REGION`, optional `ECR_REPOSITORY_URI`; `development` environment: `AWS_DEPLOY_ROLE_ARN`, `INSTANCE_ID`, `DEPLOY_DOCUMENT`, `PUBLIC_URL`), and that rerunning only a failed `deploy-dev` reuses `build-and-push`'s tag (it deploys that run's commit, not the new tip of `main`).
- **Checks:** `uvx --with shellcheck-py --from actionlint-py actionlint -verbose` (actionlint 1.7.12 with shellcheck on the `run:` blocks) reports 0 errors. Read through the file for the criteria above. Not run: the workflow itself, any AWS call or any push (user only).

Notes for QA / the PM:

- #236 is not merged into this branch's base (`github-oidc-stack.yaml` and its README section still describe the old roles), so the README table names the development deploy role without an output name. The old section about `AWS-RunShellScript` is #236's to rewrite and I left it.
- `ECR_REPOSITORY_URI` as a repo variable is an addition the criteria do not list; it is optional and only saves `build.sh` an `sts get-caller-identity` call. Remove it if the PM wants exactly the listed variables.
- The `deploy-dev` job checks out the commit only to create the `deployed-dev` tag; the deploy itself uses nothing from the checkout.

## QA: PASS

Read `.github/workflows/ci.yaml` and `infra/README.md` against each criterion. The workflow was not run and nothing touched AWS or GitHub.

- [x] `build-and-push` then `deploy-dev`, both gated on `github.event_name == 'push' && github.ref == 'refs/heads/main'`; `build-and-push` needs `[backend, frontend, stack]`, `deploy-dev` needs `[build-and-push]`; the concurrency group is unchanged - PASS
- [x] `build-and-push`: `id-token: write`, no `environment:`, assumes `vars.ECR_PUSH_ROLE_ARN` in `vars.AWS_REGION`, runs `infra/build.sh` once (arm64, QEMU and buildx pinned to SHAs), outputs the last stdout line as `tag` (also checked against the tag pattern). `build.sh` sends docker output to stderr and prints the tag last. No other job builds or pushes, and no job calls CloudFormation or `deploy.sh` (grep of `.github/workflows` finds only the `build.sh` call) - PASS
- [x] `deploy-dev`: `environment: development`, `id-token: write` and `contents: write` on this job only, assumes the deploy role var. The first step fails with a single `::error::` line naming any empty one of the five variables. The tag comes in through job-level `env:` and no `${{ }}` appears inside any `run:` - PASS
- [x] `aws ssm send-command` with `--document-name "$DEPLOY_DOCUMENT"`, `--instance-ids "$INSTANCE_ID"`, `--parameters "tag=$TAG"`. It polls `get-command-invocation` (up to 30 min) and prints stdout and stderr, then exits 1 unless the status is `Success`. No CloudFormation or `AWS-RunShellScript` - PASS
- [x] Health poll: 24 x 5 s (about 2 min), passes on 200 and `.version == $TAG`. On timeout it prints the expected tag and the last body and exits 1. No rollback - PASS
- [x] Smoke test is GET only: `/` must return 200 with a `text/html` content type, and `/api/plants` must return 200 with a non-empty array. `git tag -f deployed-dev` and the forced push are the final step, so any earlier failure skips them (no `if: always()`) - PASS
- [x] All actions are pinned to full SHAs with tag comments; both checkouts use `persist-credentials: false`; the push uses the job token over HTTPS; `actionlint` reports 0 errors. `infra/README.md` ("CI: build and deploy to dev") covers the flow, the variables (repo: `ECR_PUSH_ROLE_ARN`, `AWS_REGION`; `development` environment: the rest) and that rerunning only a failed `deploy-dev` reuses `build-and-push`'s tag - PASS

Observations, not failures:
- `ECR_REPOSITORY_URI` is an optional extra repo variable beyond the listed ones.
- The README's old `AWS-RunShellScript` section is #236's to rewrite.

Commands run:
- `uvx --with shellcheck-py --from actionlint-py actionlint -verbose`: 0 errors, shellcheck active on the `run:` blocks
- Reads and greps of `ci.yaml`, `infra/README.md`, `infra/build.sh` and `.github/workflows/`

Tests: none apply (config only); no pytest run.
