# [env] One deploy role per GitHub environment

## Goal

`infra/github-oidc-stack.yaml` (live stack `fernslop-github`) holds one deploy role for `development` and one for `production`. Each role trusts only its own GitHub environment and can only send its own SSM deploy document ([#235](235-env-build-and-deploy-by-tag.md)) to its own instance. CI no longer uses CloudFormation, so there is no CloudFormation role and no permissions boundary. The user applies it live.

## Acceptance criteria

- [ ] `CloudFormationRole`, `DeployRole` and `TrustSubject` are gone. The template has `DevelopmentDeployRole` and `ProductionDeployRole`, takes `AppPrefix` (same pattern as [#234](done/234-env-parameterise-stacks.md)), and outputs both ARNs. `aws cloudformation validate-template` and `uvx cfn-lint` pass
- [ ] `GitHubOidcProvider` keeps its logical ID and has `DeletionPolicy: Retain` and `UpdateReplacePolicy: Retain`, so deleting the stack or an update leaves the account's provider in place. The provider's change-set row is not `Remove` or `Replacement`
- [ ] Each trust policy allows `sts:AssumeRoleWithWebIdentity` with `aud` = `sts.amazonaws.com` and `sub` exactly `repo:<GitHubRepo>:environment:development` or `...:environment:production`. No wildcard, no `ref:refs/heads/main` subject
- [ ] Each role's only actions are `ssm:SendCommand` and `ssm:GetCommandInvocation`/`ssm:ListCommandInvocations`. `SendCommand` is allowed on document `<stack name>-deploy` (`fernslop-deploy`, `prod-fernslop-deploy`) and on instances whose `ssm:resourceTag/Name` equals the stack name (`fernslop`, `prod-fernslop`). Read it in the template. No `cloudformation:`, `ecr:`, `s3:`, `iam:` or `ec2:` action
- [ ] `aws iam simulate-custom-policy` on the dev role's policy allows `SendCommand` on `fernslop-deploy` with an instance tagged `Name=fernslop`. It denies `prod-fernslop-deploy`, `AWS-RunShellScript`, an instance tagged `Name=prod-fernslop`, `ecr:PutImage`, `cloudformation:ExecuteChangeSet`, `iam:PassRole` and `s3:GetObject`. The prod role mirrors this (allows its own, denies dev's)
- [ ] The "GitHub Actions deploy role" section of `infra/README.md` is rewritten for this stack. In order, it has the user: create a change set for `fernslop-github` and check that the provider is untouched and the two old roles are removed; execute it (the old CI deploy stops until [#238](238-env-ci-build-and-deploy-dev.md)); create the GitHub environments `development` and `production`; restrict `production` to deployments from `main`; set `AWS_DEPLOY_ROLE_ARN`, `AWS_REGION`, `INSTANCE_ID`, `DEPLOY_DOCUMENT` and `PUBLIC_URL` on each environment. Prod's values wait for [#237](237-env-prod-stack-and-cutover.md)
- [ ] The README also says that the ECR push role is in `ecr-stack.yaml` ([#235](235-env-build-and-deploy-by-tag.md)) and reuses this stack's provider. Its ARN and the repository URI are outputs of that stack and become the repo variables `ECR_PUSH_ROLE_ARN` and `ECR_REPOSITORY_URI`, next to the repo-level `AWS_REGION` It says what a deploy role can do (run the one document with a tag matching `allowedPattern`) and that CloudFormation changes stay manual with operator credentials

## Out of scope

- The ECR push role (OIDC subject `main` only), tag immutability and the lifecycle rule: [#235](235-env-build-and-deploy-by-tag.md). The SSM document itself: [#235](235-env-build-and-deploy-by-tag.md)
- Workflows that use the deploy roles and the `ECR_*` variables: [#238](238-env-ci-build-and-deploy-dev.md) (dev), [#239](239-env-ci-promote-to-prod.md) (prod). Creating prod and the live runbook: [#237](237-env-prod-stack-and-cutover.md) and the user
- [#233](parked/233-ci-deploy-iam-hardening.md) (hardening the CloudFormation role) no longer applies. The orchestrator closes it

## Constraints

- Change only `infra/github-oidc-stack.yaml` and that README section. Nobody but the user writes to AWS: agents may run only `validate-template`, `simulate-custom-policy` and `describe`/`get`/`list`. No new dependencies


## Engineer:

Changed only `infra/github-oidc-stack.yaml` and the "GitHub Actions deploy roles" section of `infra/README.md`. No tests: this is config.

- **Template:** `CloudFormationRole`, `DeployRole`, `TrustSubject` and the `TrustMain` condition are gone. New `DevelopmentDeployRole` and `ProductionDeployRole`, parameter `AppPrefix` (same pattern as #234), outputs `DevelopmentDeployRoleArn` and `ProductionDeployRoleArn`. `GitHubOidcProvider` keeps its logical ID and gains `DeletionPolicy: Retain` and `UpdateReplacePolicy: Retain`.
- **Trust:** `aud` = `sts.amazonaws.com`, `sub` exactly `repo:<GitHubRepo>:environment:development` / `...:environment:production`. No wildcard, no `ref:` subject.
- **Rights:** `ssm:SendCommand` on `document/<prefix>-deploy` (`prod-<prefix>-deploy`), `ssm:SendCommand` on `instance/*` with `ssm:resourceTag/Name` = `<prefix>` (`prod-<prefix>`), and `ssm:GetCommandInvocation`/`ssm:ListCommandInvocations` on `*` (they take no resource). No other action.
- **Kept `CreateOidcProvider` and `ExistingOidcProviderArn`:** the issue does not name them, and the live stack has `CreateOidcProvider=true` (read with `describe-stacks`), so the provider stays a conditional resource and the change set leaves it alone.
- **README:** the section is rewritten in the order the issue asks (change set and check, execute, create environments, restrict `production` to `main`, set the five variables), and says the ECR push role lives in `ecr-stack.yaml`, its two outputs become `ECR_PUSH_ROLE_ARN` and `ECR_REPOSITORY_URI` beside repo-level `AWS_REGION`, what a deploy role can do, and that CloudFormation stays manual. The change-set command omits the removed `TrustSubject` and uses `UsePreviousValue` for the rest.
- **Checks:** `uvx cfn-lint` clean; `aws cloudformation validate-template` passes. `aws iam simulate-custom-policy` on each role's policy (resolved from the template, placeholder account and region): the dev role allows `SendCommand` on `fernslop-deploy` and on an instance tagged `Name=fernslop`, plus the two read actions; it denies (implicit) `prod-fernslop-deploy`, `AWS-RunShellScript`, an instance tagged `Name=prod-fernslop`, an untagged instance, `ecr:PutImage`, `cloudformation:ExecuteChangeSet`, `iam:PassRole` and `s3:GetObject`. The prod role mirrors this (allows `prod-fernslop-deploy` and `prod-fernslop`, denies dev's). Not run: the live change set, which only the user can create. The provider row cannot be seen until then; the template-level reason it stays untouched is that its logical ID, condition, properties and parameters are unchanged.
- **For #238:** `deploy.sh` still reads `CFN_ROLE_ARN` (not a file this issue names); with the CloudFormation role gone nothing sets it. #233 (parked) no longer applies; the orchestrator closes it.


## QA: PASS

- [x] `CloudFormationRole`, `DeployRole`, `TrustSubject` gone; `DevelopmentDeployRole` and `ProductionDeployRole` exist; `AppPrefix` (pattern `^[a-z0-9-]+$`) present; both ARNs are outputs; validate-template and cfn-lint pass - PASS
- [x] `GitHubOidcProvider` keeps its logical ID, has `DeletionPolicy: Retain` and `UpdateReplacePolicy: Retain` - PASS
      The live stack (`fernslop-github`, CREATE_COMPLETE, `CreateOidcProvider=true`) has the same provider logical ID, condition, `Url` and `ClientIdList` as the new template (compared with `get-template`), so no `Remove` or `Replacement` row is expected. The change-set row itself cannot be seen: QA may not create change sets. The live change set stays the user's check (README step 1).
- [x] Trust policies: `sts:AssumeRoleWithWebIdentity`, `aud` = `sts.amazonaws.com`, `sub` exactly `repo:${GitHubRepo}:environment:development` / `...:environment:production`; no wildcard, no `ref:` subject - PASS (read in the template; grep for `ref:refs` finds nothing)
- [x] Actions are only `ssm:SendCommand` (document `<prefix>-deploy` / `prod-<prefix>-deploy`; instances with `ssm:resourceTag/Name` = `<prefix>` / `prod-<prefix>`) and `ssm:GetCommandInvocation`/`ssm:ListCommandInvocations`; no `cloudformation:`, `ecr:`, `s3:`, `iam:` or `ec2:` action - PASS
- [x] `simulate-custom-policy` (policy extracted from the template with `AppPrefix=fernslop`, account `123456789012`, region `eu-west-2`) - PASS
      Dev role: allowed `SendCommand` on `document/fernslop-deploy`, on an instance with `ssm:resourceTag/Name=fernslop`, and both read actions. implicitDeny: `document/prod-fernslop-deploy`, `document/AWS-RunShellScript`, an instance tagged `prod-fernslop`, an untagged instance, `ecr:PutImage`, `cloudformation:ExecuteChangeSet`, `iam:PassRole`, `s3:GetObject`.
      Prod role: allowed `document/prod-fernslop-deploy`, an instance tagged `prod-fernslop`, and both read actions. implicitDeny: `document/fernslop-deploy`, `AWS-RunShellScript`, an instance tagged `fernslop`, an untagged instance and the same four other actions.
- [x] README "GitHub Actions deploy roles" section is rewritten in the required order: change set and check (provider absent, old roles `Remove`, new roles `Add`), execute (old CI deploy stops until #238), create `development` and `production` environments, restrict `production` to `main`, set `AWS_DEPLOY_ROLE_ARN`, `AWS_REGION`, `INSTANCE_ID`, `DEPLOY_DOCUMENT`, `PUBLIC_URL` per environment; prod values wait for #237 - PASS
- [x] README says the ECR push role is in `ecr-stack.yaml` (#235) and reuses this stack's provider; `EcrPushRoleArn`/`RepositoryUri` become `ECR_PUSH_ROLE_ARN`/`ECR_REPOSITORY_URI` next to repo-level `AWS_REGION`; says a deploy role runs only the one document with a tag matching `allowedPattern`; CloudFormation changes stay manual with operator credentials - PASS

Commands run (read-only): `uvx cfn-lint infra/github-oidc-stack.yaml` (no findings); `aws cloudformation validate-template --template-body file://infra/github-oidc-stack.yaml` (valid; parameters AppPrefix, GitHubRepo, CreateOidcProvider, ExistingOidcProviderArn); `aws cloudformation describe-stacks`, `list-stack-resources` and `get-template --stack-name fernslop-github`; 24 `aws iam simulate-custom-policy` calls (12 per role) as listed above.

Tests: no test suite applies (config and docs only). Nothing in the code was changed.

Note for #238 (not a failure): the live stack still has the old `CloudFormationRole`/`DeployRole`/`TrustSubject` until the user executes the change set. `deploy.sh` still reads `CFN_ROLE_ARN`, as the engineer said.
