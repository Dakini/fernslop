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
