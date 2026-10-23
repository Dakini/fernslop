# [env] Build once by tag, and deploy a tag through a stack-owned SSM document

## Goal

`infra/build.sh` builds and pushes one arm64 image per commit, tagged `YYYYMMDD-HHMMSS-shortsha`. Each stack owns an SSM document that runs an existing tag, so CI (#238, #239) and the operator's `deploy.sh <env> <tag>` deploy by tag and never touch CloudFormation or `AWS-RunShellScript`.

## Acceptance criteria

- [ ] `infra/build.sh --print-tag` prints the tag without calling AWS or docker: the HEAD commit's committer time in UTC plus the 7-char sha (the same commit always gives the same tag; works on macOS and Linux). A build refuses a dirty tree, skips the push when the tag is already in ECR, builds with `--build-arg FERNSLOP_IMAGE_TAG=<tag>` ([#229](done/229-ci-deploy-version-check.md)), pushes only `<repo>:<tag>` (no `:latest`) and prints the tag as its last stdout line
- [ ] `ec2-stack.yaml` has an `AWS::SSM::Document` `<stack name>-deploy` (`fernslop-deploy`, `prod-fernslop-deploy`) with one parameter `tag`, `allowedPattern` `^[0-9]{8}-[0-9]{6}-[0-9a-f]{7}$`. It logs in to ECR, sets `APP_TAG=<tag>` in `/opt/app/.env`, runs `docker compose up -d --pull always`, then `docker image prune -f`. A stack output gives its name
- [ ] The compose file's app image is `<repo>:${APP_TAG}`, read from `/opt/app/.env`; no file references `:latest`. A stack takes an `ImageTag` parameter (same pattern) that a new or replaced instance boots; later deploys never change it. The document replaces only the `APP_TAG=` line, and fails with a clear message if the compose file has no `${APP_TAG}`, so an old instance never silently re-pulls `:latest`
- [ ] `deploy.sh <env> <tag>` refuses a missing tag, a bad format or a tag not in ECR (read-only `describe-images`) with a one-line message, before any change. It has no `docker build`. It sends the stack's document, waits for it, then requires `/api/health` `version == <tag>`. It no longer deploys the ECR stack; a first creation passes `ImageTag=<tag>`, an update keeps the previous one
- [ ] `ecr-stack.yaml` sets `ImageTagMutability: IMMUTABLE`, expires untagged images after 1 day and keeps the last 50 tagged ones. It adds a push role: OIDC subject `repo:<owner/repo>:ref:refs/heads/main` only, ECR push and `DescribeImages` on this repository only, no deploy rights. It never creates the OIDC provider (`fernslop-github` owns it, #236); a required `ExistingOidcProviderArn` parameter names it. Stack outputs `EcrPushRoleArn` and `RepositoryUri` become the repo variables `ECR_PUSH_ROLE_ARN` and `ECR_REPOSITORY_URI`
- [ ] `infra/README.md` has a runbook the user runs once, after #234's: apply the `<prefix>-ecr` change set (`ExistingOidcProviderArn` from `aws iam list-open-id-connect-providers`), run `build.sh`, create (not execute) the `fernslop` change set (new document, no `Replacement`), execute it, edit the live dev compose app image from `:latest` to `:${APP_TAG}` in an SSM session, then `deploy.sh dev <tag>`; each step says how to check it, and tolerates the older instance files ([#234](done/234-env-parameterise-stacks.md) comment)
- [ ] `deploy.sh` and `build.sh` pass `bash -n` and `shellcheck`; both templates pass `uvx cfn-lint`

## Out of scope

- Deploy roles (only `ssm:SendCommand` on that document and that instance), GitHub environments and variables: [#236](236-env-iam-split-per-environment.md)
- Workflows, the `deployed-dev` tag and the health comparison in CI: [#238](238-env-ci-build-and-deploy-dev.md), [#239](239-env-ci-promote-to-prod.md); creating prod: [#237](237-env-prod-stack-and-cutover.md)
- Backups and other files the live dev instance lacks: not part of this switch; rollback: [#230](parked/230-ci-deploy-rollback.md)

## Constraints

- Only `infra/build.sh` (new), `deploy.sh`, `ec2-stack.yaml`, `ecr-stack.yaml`, `README.md`; keep dev's physical names and the instance `Name` tag (`fernslop`, `prod-fernslop`) exactly as #234 set it: IAM scopes instances by it. Do not set `FERNSLOP_IMAGE_TAG` at run time
- Agents run only read-only AWS commands; the user runs builds, deploys and change sets. `shellcheck` and `cfn-lint` via `uvx` or brew, not `pyproject.toml`. Tags older than the last 50 builds expire, so a long-lagging prod loses its image on the next pull
