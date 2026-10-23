# [env] Parameterise the stacks by app prefix, environment and domain

## Goal

`infra/ec2-stack.yaml`, `ecr-stack.yaml` and `deploy.sh` take an app prefix (`APP_PREFIX`, default `fernslop`), an environment (`dev`/`prod`) and a domain as inputs, so a prod stack can run next to today's live stacks (which become dev) and a fork can pick its own names. Dev resolves to exactly today's names.

## Acceptance criteria

- [ ] `infra/deploy.sh <env> --names` prints the resolved names without calling AWS. For `dev` with the default prefix they are today's: stacks `fernslop` and `fernslop-ecr`, log group `/fernslop/app`, dashboard `fernslop`, instance tag `Name=fernslop`, ECR repo `fernslop`
- [ ] For `prod` they start with `prod-<prefix>` (stack `prod-fernslop`, log group `/prod-fernslop/app`), so neither they nor the names CloudFormation generates from the stack name match the `fernslop-*` / `/fernslop/app*` patterns in `github-oidc-stack.yaml`. Both environments use the one shared `<prefix>` ECR repo and `<prefix>-ecr` stack
- [ ] `deploy.sh` refuses a missing or unknown environment, a prefix that is not lowercase letters, digits and hyphens, and a `DOMAIN` that differs from an existing stack's `DomainName` (that switch is #237's runbook), each with a one-line message
- [ ] Every resource that supports tags carries `App=<prefix>` and `Environment=<env>`
- [ ] The backup script sends `BackupSucceeded` with an `Environment` dimension, and `BackupMissingAlarm` and the dashboard read it, so a prod backup cannot hide a missing dev one
- [ ] On update, `deploy.sh` keeps the running instance's AMI (today the SSM `LatestAmiId` re-resolves on every update, so a newer AL2023 image would replace the instance)
- [ ] `infra/README.md` has a runbook the user runs, in order: update the dev instance's `/usr/local/bin/fernslop-backup` via SSM, then create (not execute) change sets for `fernslop-ecr` and `fernslop`, and check that no resource shows `Replacement` `True` or `Conditional`; the only Instance change is `UserData` (a short stop/start) and tags. Both templates pass `uvx cfn-lint` or `aws cloudformation validate-template`

## Out of scope

- Build once by tag, tag immutability, ECR expiry vs prod's tag, `deploy.sh <env> <tag>`: [#235](235-env-build-and-deploy-by-tag.md)
- Per-environment GitHub and CloudFormation roles (today's roles cannot reach `prod-*` names): [#236](236-env-iam-split-per-environment.md)
- Creating prod, moving data, DNS and dev's new domain: [#237](237-env-prod-stack-and-cutover.md); CI deploys: [#238](238-env-ci-build-and-deploy-dev.md), [#239](239-env-ci-promote-to-prod.md)
- `FERNSLOP_*` vars, Postgres user/db, `/opt/app`, systemd unit names, metric namespace `Fernslop`: [#240](parked/240-env-app-level-naming.md)

## Constraints

- Only `infra/ec2-stack.yaml`, `ecr-stack.yaml`, `deploy.sh` and `README.md`; not `github-oidc-stack.yaml` or `.github/workflows/ci.yaml`
- Environment is `deploy.sh`'s first argument, the domain moves to `DOMAIN=` so #235 can add `<tag>`; keep the build, `:latest`, `ALLOW_PLAIN_HTTP` and `CFN_ROLE_ARN` as they are
- For dev, keep every physical name and the security group description identical: changing one replaces the resource
- Agents run only read-only AWS commands (validate, describe); the user creates and executes every change set. `cfn-lint` runs via `uvx`, not added to `pyproject.toml`
