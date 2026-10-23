# [env] Build the image once by tag, and deploy only existing tags

## Goal

`infra/build.sh` builds and pushes one arm64 image per commit, tagged `YYYYMMDD-HHMMSS-shortsha` (UTC), to the shared `<prefix>` ECR repo (#234). `infra/deploy.sh <env> <tag>` never builds: it runs that tag on the environment's instance and records it once healthy, so #238 and #239 can deploy and promote exact tags instead of `:latest`.

## Acceptance criteria

- [ ] `infra/build.sh` refuses a dirty working tree, builds with `--build-arg FERNSLOP_IMAGE_TAG=<tag>` (so `/api/health` reports it, [#229](229-ci-deploy-version-check.md)), pushes only `<repo>:<tag>` (no `:latest`) and prints the tag as its last stdout line. `infra/build.sh --print-tag` prints the tag it would use without building or calling AWS
- [ ] `deploy.sh <env> <tag>` refuses a missing tag, a tag not matching the format, or a tag not in ECR (read-only `describe-images`), with a one-line message, before any change. It contains no `docker build`
- [ ] On an existing stack, a deploy changes no CloudFormation resource (the update path keeps the previous `ImageTag` parameter, so `UserData` never changes): it writes the tag to the instance via SSM and runs `docker compose up -d`
- [ ] After `/api/health` passes, and only then, `deploy.sh` writes the tag to the SSM parameter `/<stack name>/deployed-tag`. A new or replaced instance boots that recorded tag, else the stack's `ImageTag`; no compose file or script references `:latest`
- [ ] `ecr-stack.yaml` sets `ImageTagMutability: IMMUTABLE`. Deploying to prod also adds a `prod-<tag>` tag to the image, and a lifecycle rule ahead of "keep the last 10" keeps the last 5 `prod-` images, so prod's tag never expires however many dev builds follow
- [ ] `infra/README.md` has a runbook the user runs once, after #234's: execute the `<prefix>-ecr` change set, run `build.sh`, switch the live dev compose file's app image from `:latest` to the tag (by hand in an SSM session), then `deploy.sh dev <tag>` and check `/api/health` shows that tag
- [ ] `deploy.sh` and `build.sh` pass `bash -n` and `shellcheck`; both templates pass `uvx cfn-lint`

## Out of scope

- The tag in `/api/health`: [#229](229-ci-deploy-version-check.md); comparing it after deploy: [#238](238-env-ci-build-and-deploy-dev.md), [#239](239-env-ci-promote-to-prod.md)
- Deploy-role permissions for the SSM parameter and for adding `prod-` tags (`ecr:PutImage`): [#236](236-env-iam-split-per-environment.md)
- Pushing file changes to the running instance automatically: [#208](parked/208-audit-apply-to-running-instance.md) (parked); rollback: [#230](parked/230-ci-deploy-rollback.md)

## Constraints

- After #234 (its names, `deploy.sh <env>` and `DOMAIN=`). Only `infra/build.sh` (new), `deploy.sh`, `ec2-stack.yaml`, `ecr-stack.yaml`, `README.md`
- The instance role may read only its own `deployed-tag` parameter; keep dev's physical names unchanged
- Agents run only read-only AWS commands; the user runs builds, deploys and change sets. `shellcheck`/`cfn-lint` via `uvx` or brew, not `pyproject.toml`
