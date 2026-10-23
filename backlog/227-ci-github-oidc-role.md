# [ci] CloudFormation stack for a GitHub OIDC deploy role

## Goal

New `infra/github-oidc-stack.yaml` (stack `fernslop-github`, deployed once by the user with operator credentials) gives `Dakini/fernslop` an IAM role that GitHub Actions can assume via OIDC to run `infra/deploy.sh` against the existing `fernslop-ecr` and `fernslop` stacks (#228). No long-lived AWS keys. Open user decisions (main vs `production` environment; provider exists or not) are parameters, not blockers.

## Acceptance criteria

- [ ] Parameters: `GitHubRepo` (default `Dakini/fernslop`); `TrustSubject` (`main` default, or `production-environment`); `CreateOidcProvider` (`true` default / `false`) and `ExistingOidcProviderArn` (default empty). A `Rules` assert fails the deploy when `CreateOidcProvider=false` and the ARN is empty.
- [ ] With `CreateOidcProvider=true` the stack creates `AWS::IAM::OIDCProvider` for `https://token.actions.githubusercontent.com` with client ID `sts.amazonaws.com`. With `false` it creates none and the role trusts the given ARN.
- [ ] The deploy role's trust policy allows only `sts:AssumeRoleWithWebIdentity` with `StringEquals` (no `StringLike`, no `*`) on `token.actions.githubusercontent.com:aud` = `sts.amazonaws.com` and `:sub` = `repo:<GitHubRepo>:ref:refs/heads/main` or `repo:<GitHubRepo>:environment:production`. `MaxSessionDuration` is 3600.
- [ ] The deploy role has no IAM write. It can: run change sets on `fernslop` and `fernslop-ecr` (create, describe, execute, describe stacks and events, `GetTemplateSummary`), `iam:PassRole` only on this stack's CloudFormation service role, push to ECR repository `fernslop` (`ecr:GetAuthorizationToken` on `*`), `ssm:SendCommand` on `AWS-RunShellScript` plus instances tagged `Name=fernslop` (with `ssm:GetCommandInvocation`/`ListCommandInvocations` for the wait). No S3 access at all, so it cannot read the backup dumps.
- [ ] A CloudFormation service role (trusted by `cloudformation.amazonaws.com` only) holds the rights to update both stacks: the resource types in `ec2-stack.yaml` and `ecr-stack.yaml`, with IAM rights limited to `role/fernslop-*` and `instance-profile/fernslop-*`. `infra/deploy.sh` passes `--role-arn "$CFN_ROLE_ARN"` to both `cloudformation deploy` calls only when that variable is set. Nothing changes for the operator otherwise.
- [ ] Outputs `DeployRoleArn` and `CloudFormationRoleArn`. `infra/README.md` gets a short section: the one-time `aws cloudformation deploy ... --capabilities CAPABILITY_IAM` command for each choice, how to look up an existing provider ARN (`aws iam list-open-id-connect-providers`), and the GitHub variables #228 reads (`AWS_DEPLOY_ROLE_ARN`, `AWS_CFN_ROLE_ARN`, `AWS_REGION`). It also notes that `production-environment` only works once the GitHub `production` environment exists and the deploy job uses it.
- [ ] `aws cloudformation validate-template --template-body file://infra/github-oidc-stack.yaml` succeeds (credentials are configured; `cfn-lint` is not installed). `bash -n infra/deploy.sh` passes. Never `create-stack`/`deploy` it: the user deploys it.

## Out of scope

- The workflow job that assumes the role and runs the deploy: #228
- Region fallback in `deploy.sh` and the CI-only update path: #228
- Creating the GitHub `production` environment and its reviewers: the user does this, it is not in the repo

## Constraints

- Only `infra/github-oidc-stack.yaml` (new), `infra/deploy.sh` (the optional `--role-arn` only) and `infra/README.md`. No new dependencies, no pytest tests: verification is `validate-template` plus a review of the policies against the criteria above.
- Match `ec2-stack.yaml` style (inline policies, `!Sub` ARNs with `${AWS::Region}`/`${AWS::AccountId}`).
