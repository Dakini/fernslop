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

## Engineer:

Added `infra/github-oidc-stack.yaml`, the optional `--role-arn` in `infra/deploy.sh`, and a "GitHub Actions deploy role" section in `infra/README.md`. No tests: this is config.

- **Parameters and rule:** `GitHubRepo`, `TrustSubject` (`main` | `production-environment`), `CreateOidcProvider` and `ExistingOidcProviderArn`. The `ProviderArnRequired` rule fails the deploy when the provider flag is `false` and the ARN is empty. The provider is conditional (`url` token.actions.githubusercontent.com, client ID `sts.amazonaws.com`, no thumbprint, which is optional now). The role's `Federated` principal is `!If` provider / given ARN.
- **Trust:** only `sts:AssumeRoleWithWebIdentity`, with `StringEquals` on `aud` and `sub` (`repo:<GitHubRepo>:ref:refs/heads/main` or `repo:<GitHubRepo>:environment:production`). `MaxSessionDuration: 3600`.
- **Deploy role:** no IAM write and no S3.
  - CloudFormation: Describe/Execute change sets and DescribeStacks/Events on `stack/fernslop/*` and `stack/fernslop-ecr/*`. `CreateChangeSet` is also limited by `cloudformation:RoleArn` = the service role, so a change set can never run with the deploy role's own rights. `GetTemplateSummary` is on `*` because it takes a template, not a stack.
  - `iam:PassRole` only on the service role, and only to `cloudformation.amazonaws.com`.
  - ECR: `GetAuthorizationToken` on `*`, plus the push actions on `repository/fernslop`.
  - SSM: `SendCommand` on `document/AWS-RunShellScript` and on instances tagged `Name=fernslop`, plus `GetCommandInvocation`/`ListCommandInvocations` on `*` (they take no resource).
  - Read-only additions: the `aws cloudformation deploy` change-set ARN pattern, `ssm:GetParameters` on the public AL2023 AMI parameter, and `ec2:DescribeVpcs`/`DescribeSubnets`. CloudFormation may resolve and check `ec2-stack.yaml`'s `LatestAmiId`/`VpcId`/`SubnetId` parameter types with the caller's rights.
- **Tag condition check (PM assumption):** the condition is sound. `ec2-stack.yaml` tags the instance `{ Key: Name, Value: fernslop }`. The AWS docs ("Setting up Run Command", restricting by tags) use exactly this pattern: `ssm:SendCommand` on `arn:aws:ec2:*:*:instance/*` with condition `ssm:resourceTag/<key>`, and the document in a separate statement without the condition. A document has no tag, so a combined statement would always be denied. That is why there are two statements. An instance-ARN pattern would be worse: the instance ID changes when the instance is replaced, and this stack cannot import it (`ec2-stack.yaml` has no export and is out of scope), so the pattern would have to be `instance/*`, which means every instance in the region. The deploy role has no `ec2:CreateTags`, so it cannot tag another instance `Name=fernslop` directly.
- **CloudFormation service role** (trusted by `cloudformation.amazonaws.com` only), with rights for each resource type in both stacks:
  - ECR on `repository/fernslop`.
  - EC2 instance, security group, EIP, metadata options and tags, limited to this region by `aws:RequestedRegion`. EC2 resources are named by generated IDs, so they cannot be scoped by name.
  - IAM only on `role/fernslop-*` and `instance-profile/fernslop-*`. `Attach`/`DetachRolePolicy` are limited to `AmazonSSMManagedInstanceCore`, and `PassRole` only to `ec2.amazonaws.com`.
  - S3 bucket configuration only, on `fernslop-backupbucket-*`, with no object actions.
  - Logs on `/fernslop/app`, CloudWatch alarms `fernslop-*` and dashboard `fernslop`.
  - An explicit **Deny on `iam:*` for `role/fernslop-github-*`**. This stack's own roles also match `fernslop-*`. Without the deny, a template run as the service role could use `AWS::IAM::RolePolicy` to widen the deploy role or the service role itself.
- **deploy.sh:** all three `aws cloudformation deploy` calls (the ECR stack, the update branch and the create branch) end with `${CFN_ROLE_ARN:+--role-arn "$CFN_ROLE_ARN"}`. When the variable is unset or empty this expands to no words, also under `set -u` with macOS `/bin/bash` 3.2, so the operator command line is unchanged. When it is set, it adds exactly `--role-arn <arn>`. I checked this with a stub script that prints the argv.
- **Verification:** `aws cloudformation validate-template --template-body file://infra/github-oidc-stack.yaml` succeeds (Capabilities `CAPABILITY_IAM`, 4 parameters). `bash -n infra/deploy.sh` passes. Nothing was created or deployed.
- **Residual risks (not fixable inside this issue's files):**
  - Whoever can push to `main`, or approve `production`, can change `ec2-stack.yaml`, including the instance role's inline policy. That is inherent to deploying infra from CI, and the README says so. A follow-up could add a permissions boundary to `InstanceRole` and require it in the service role.
  - The recovery alarm's EC2 action needs the `AWSServiceRoleForCloudWatchEvents` service-linked role. It already exists in an account where the stack was created, so the service role gets no `iam:CreateServiceLinkedRole`.
  - I could not open the Service Authorization Reference page here to confirm whether IAM checks change-set actions against the stack ARN alone. The narrow `changeSet/awscli-cloudformation-package-deploy-*/*` ARN covers the other case.
