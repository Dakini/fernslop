# Infra

Fernslop runs on one EC2 instance (docker compose: `db`, `app`, `caddy`). Its CloudFormation stacks, set up once:

| Stack | Template | What it is |
| --- | --- | --- |
| `fernslop-github` | `github-oidc-stack.yaml` | GitHub OIDC login and the deploy roles CI uses |
| `fernslop-ecr` | `ecr-stack.yaml` | the image repository and the role CI uses to push |
| `fernslop` / `prod-fernslop` | `ec2-stack.yaml` | the dev and prod servers (made by `deploy.sh`) |

Prod is a second server stack, `prod-fernslop`. After setup, a push to `main` tests, builds, pushes and deploys to dev; prod is promoted by hand. You do not touch AWS again.

## Set up CI/CD

Needs the `aws` and `gh` CLIs, logged in. Run from the repo root. Region is `eu-west-2`. Replace `<owner>/<repo>` with your GitHub repo.

**1. Your repo's GitHub name.** AWS only lets in jobs whose GitHub identity matches this exactly.

```sh
gh api repos/<owner>/<repo>/actions/oidc/customization/sub
```

If it shows `"use_immutable_subject":true`, use the `sub_claim_prefix` without `repo:` (e.g. `<owner>@<owner id>/<repo>@<repo id>`). Otherwise use `<owner>/<repo>`. Call it `REPO`:

```sh
REPO='<owner>/<repo>'     # or the immutable form
```

A wrong name fails in CI with `Not authorized to perform sts:AssumeRoleWithWebIdentity`. Fix it by rerunning step 2 with the right `REPO`.

**2. The two CI stacks.** `deploy` creates a stack or updates it, so rerunning is safe.

```sh
aws cloudformation deploy --stack-name fernslop-github --template-file infra/github-oidc-stack.yaml \
  --capabilities CAPABILITY_IAM --parameter-overrides GitHubRepo="$REPO"

PROVIDER=$(aws iam list-open-id-connect-providers \
  --query "OpenIDConnectProviderList[?contains(Arn,'token.actions')].Arn" --output text)
aws cloudformation deploy --stack-name fernslop-ecr --template-file infra/ecr-stack.yaml \
  --capabilities CAPABILITY_IAM --parameter-overrides GitHubRepo="$REPO" ExistingOidcProviderArn="$PROVIDER"
```

`CAPABILITY_IAM` is typed as is, not a variable: it allows the stacks to create IAM roles.

(If the account already had a GitHub OIDC provider before `fernslop-github`, add `CreateOidcProvider=false ExistingOidcProviderArn=<arn>` to that stack's overrides.)

**3. GitHub variables.** Read the outputs, then set them. The repo ones are shared; each environment gets its own `AWS_DEPLOY_ROLE_ARN`.

```sh
aws cloudformation describe-stacks --stack-name fernslop-github --query "Stacks[0].Outputs" --output table
aws cloudformation describe-stacks --stack-name fernslop-ecr --query "Stacks[0].Outputs" --output table

gh variable set AWS_REGION --body eu-west-2
gh variable set ECR_PUSH_ROLE_ARN --body <EcrPushRoleArn>
gh variable set ECR_REPOSITORY_URI --body <RepositoryUri>

gh api -X PUT repos/<owner>/<repo>/environments/development     # creates the environment
gh api -X PUT repos/<owner>/<repo>/environments/production
gh variable set AWS_DEPLOY_ROLE_ARN --env development --body <DevelopmentDeployRoleArn>
gh variable set AWS_DEPLOY_ROLE_ARN --env production --body <ProductionDeployRoleArn>
```

In GitHub settings, limit `production`'s deployment branches to `main`.

**4. Build an image.** Push to `main` (or re-run CI). `build-and-push` puts the image in ECR. `deploy-dev` fails with `Empty variables ... INSTANCE_ID DEPLOY_DOCUMENT PUBLIC_URL` because there is no server yet; that is expected. Get the tag:

```sh
TAG=$(aws ecr describe-images --repository-name fernslop \
  --query "sort_by(imageDetails,&imagePushedAt)[-1].imageTags[0]" --output text)
```

**5. Elastic IPs and DNS.** One IP per server, kept outside the stacks so the address survives deleting a server:

```sh
aws ec2 allocate-address --domain vpc --tag-specifications 'ResourceType=elastic-ip,Tags=[{Key=Name,Value=fernslop-dev}]'
aws ec2 allocate-address --domain vpc --tag-specifications 'ResourceType=elastic-ip,Tags=[{Key=Name,Value=fernslop-prod}]'
```

Point an A record for each domain at its IP. On Cloudflare set it to DNS only (grey cloud), or the server cannot get its HTTPS certificate. Do this before step 6.

**6. Create the servers.**

```sh
DOMAIN=dev.example.com EIP_ALLOCATION_ID=<dev eipalloc-...> EIP_ADDRESS=<dev ip> infra/deploy.sh dev "$TAG"
DOMAIN=example.com EIP_ALLOCATION_ID=<prod eipalloc-...> EIP_ADDRESS=<prod ip> infra/deploy.sh prod "$TAG"
```

Dev is the stack `fernslop`, prod is `prod-fernslop`. Each waits until `/api/health` reports the tag. Without a domain, use `ALLOW_PLAIN_HTTP=true` instead of `DOMAIN=` (`http://<ip>`). The domain cannot change later without rebuilding the server.

**7. Point CI at the servers.**

```sh
aws cloudformation describe-stacks --stack-name fernslop --query "Stacks[0].Outputs" --output table
aws cloudformation describe-stacks --stack-name prod-fernslop --query "Stacks[0].Outputs" --output table
```

Set these on each environment (`--env development` from `fernslop`, `--env production` from `prod-fernslop`):

```sh
gh variable set INSTANCE_ID --env development --body <InstanceId>
gh variable set DEPLOY_DOCUMENT --env development --body <DeployDocumentName>   # fernslop-deploy / prod-fernslop-deploy
gh variable set PUBLIC_URL --env development --body <Url>                       # https://<domain>, no trailing slash
```

Re-run the failed `deploy-dev` job. Done: every push to `main` deploys to dev, and "Promote to prod" (Actions tab, `promote.yaml`) deploys the image dev is running. Promote needs one successful `deploy-dev` first.

## If you delete a server

```sh
aws cloudformation delete-stack --stack-name fernslop          # or prod-fernslop
aws cloudformation wait stack-delete-complete --stack-name fernslop
```

Redo step 6 with the same Elastic IP, then update `INSTANCE_ID` (step 7). Do not delete the two CI stacks. The data on the server goes with it; there are no backups.

If the ECR repository was deleted by hand, stack updates fail with `repository ... does not exist`. Delete the `fernslop-ecr` stack, redo step 2 for it, then update `ECR_PUSH_ROLE_ARN` and `ECR_REPOSITORY_URI`.

## How a deploy works

- `infra/build.sh` builds the arm64 image and pushes it to ECR as `<repo>:YYYYMMDD-HHMMSS-<sha>`. The tag is baked in, so `/api/health` reports it as `version`. There is no `:latest`. ECR keeps the last 50 tags.
- Each server stack has an SSM document `<stack name>-deploy` that takes a `tag`, sets `APP_TAG` in `/opt/app/.env` and runs `docker compose up -d --pull always`. CI sends that document; it does not use CloudFormation.
- `deploy-dev` waits until `/api/health` reports the new tag, smoke-tests `/` and `/api/plants`, then moves the `deployed-dev` git tag, which is what "Promote to prod" deploys. Nothing is rolled back on failure.
- `deploy.sh` creates the server stack on the first run. On later runs it updates the stack and sends the same SSM document. Rerun a failed `deploy-dev` with "Re-run failed jobs".
