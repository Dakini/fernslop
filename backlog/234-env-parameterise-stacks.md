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

## Engineer:

Changed only `infra/deploy.sh`, `ec2-stack.yaml`, `ecr-stack.yaml` and `README.md`. No tests: this is config and a script.

- **deploy.sh:** `infra/deploy.sh <dev|prod> [--names]`, `APP_PREFIX` (default `fernslop`), `DOMAIN=`. `--names` exits before any AWS or git call. Missing/unknown environment, a bad prefix and a `DOMAIN` that differs from the stack's `DomainName` each exit 1 with one line. Build, `:latest`, `ALLOW_PLAIN_HTTP` and `CFN_ROLE_ARN` unchanged.
- **Names:** dev `fernslop`, `fernslop-ecr`, `/fernslop/app`, dashboard `fernslop`, `Name=fernslop`, repo `fernslop`; prod `prod-fernslop`, `/prod-fernslop/app`, same shared repo and ECR stack. Security group description untouched.
- **Templates:** new parameters `AppPrefix` (pattern-checked), `Environment` (dev/prod) and `AmiId`. `ImageId` is `AmiId` when set, else `LatestAmiId`. On update, `deploy.sh` passes the stack's previous `AmiId`, or the running instance's `ImageId` if there is none. CI's deploy role has no `ec2:DescribeInstances`, so this works for CI only after the runbook has set `AmiId`.
- **Tags:** `App`/`Environment` on LogGroup, SecurityGroup, InstanceRole, BackupBucket, Instance, ElasticIp, both alarms and the ECR repo. InstanceProfile, BucketPolicy, EIPAssociation and Dashboard take no tags.
- **Backups:** the script sends `--dimensions Environment=<env>`; `BackupMissingAlarm` and the dashboard widget read that dimension.
- **Runbook:** "One-time: move today's stacks onto the parameterised templates" in `infra/README.md`. Order: SSM patch of the backup script plus one backup run, ECR change set, EC2 change set (pins the current AMI), checks, then execute at a quiet time with about a minute of downtime.
- **Checks:** `uvx cfn-lint` 1.58.0 passes on both templates; `aws cloudformation validate-template` passes on both; `bash -n` ok; `--names` for dev/prod/a fork prefix and every refusal checked by hand (the `DOMAIN` one against the live stack, read-only).

Deviations and findings for QA / the PM:

- **The ECR repo is tagged `Environment=shared`, not `<env>`.** It is one repo for both environments, so tagging it with whichever env deployed last would flip the tag back and forth.
- **The live `fernslop` stack is behind the repo (read-only `get-template`/`list-stack-resources`).** It has no `BackupBucket`, `BackupBucketPolicy`, `BackupMissingAlarm` or `AllowPlainHttp` parameter, and older UserData (unpinned compose/images, a single `.env`, no Caddy limits/headers). So:
  - the dev instance has no `/usr/local/bin/fernslop-backup` for step 1 to patch (the runbook handles that case);
  - the EC2 change set will also show those resources as `Add`;
  - `BackupMissingAlarm` will go to ALARM a day after the update, because UserData does not re-run on a stop/start, so backups, the hardened compose file and the Caddy config never reach this instance.
  
  Getting them onto the dev instance (a manual install or a planned replacement) is outside #234 and needs its own issue.
- **CI permissions until #236.** The new tags need tag permissions on the CloudFormation role; it already has them for every resource type used here (`ecr:TagResource`, `iam:TagRole`, `s3:PutBucketTagging`, `logs:TagResource`, `cloudwatch:TagResource`, `ec2:CreateTags`). Nothing here needs `github-oidc-stack.yaml` changes for dev.
