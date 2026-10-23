# [ci] Follow-up: harden the GitHub deploy roles (concerns from #227 QA)
**What:** Tighten `infra/github-oidc-stack.yaml` (stack `fernslop-github`, deployed 2026-10-23 in eu-west-2) for these concerns:
1. The CloudFormation role can create or edit any `role/fernslop-*` with any policy and trust, so whoever controls a template pushed to `main` is effectively account admin. Require a permissions boundary on roles it creates or edits.
2. Backups can still be read without the deploy role having S3 rights. The CloudFormation role has `s3:PutBucketPolicy` on `fernslop-backupbucket-*`, and `AWS-RunShellScript` runs as root on an instance whose role reaches the bucket.
3. The CloudFormation role's EC2 rights cover every instance and security group in the region. A template could tag another instance `Name=fernslop`, and the deploy role could then send commands to it.
4. Once CI deploys with `--role-arn`, CloudFormation keeps that role on the stack, so later manual `deploy.sh` runs also go through it. `infra/README.md` says nothing changes for the operator, which needs correcting.
**Why:** QA on [#227](../done/227-ci-github-oidc-role.md) passed but raised these concerns. The user plans to allow changes to `main` only through PRs ([#231](231-ci-required-status-checks.md)), which mitigates 1-3 but does not remove them.
**Edge cases:** A boundary must still allow the instance role's existing policies; updating the deployed stack is a change to live IAM, so the user runs it.
