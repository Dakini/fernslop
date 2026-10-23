# Infra

Fernslop runs on one EC2 instance (docker compose: `db`, `app`, `caddy`). Three CloudFormation stacks, set up once:

| Stack | Template | What it is |
| --- | --- | --- |
| `fernslop-github` | `github-oidc-stack.yaml` | GitHub OIDC login and the deploy roles CI uses |
| `fernslop-ecr` | `ecr-stack.yaml` | the image repository and the role CI uses to push |
| `fernslop` | `ec2-stack.yaml` | the server (made by `deploy.sh`) |

After setup, a push to `main` tests, builds, pushes and deploys to dev. You do not touch AWS again.

## Set up CI/CD

Needs the `aws` and `gh` CLIs, logged in. Run from the repo root. Region is `eu-west-2`.

**1. The two CI stacks.** `deploy` creates a stack or updates it, so rerunning is safe.

```sh
aws cloudformation deploy --stack-name fernslop-github --template-file infra/github-oidc-stack.yaml \
  --capabilities CAPABILITY_IAM

PROVIDER=$(aws iam list-open-id-connect-providers \
  --query "OpenIDConnectProviderList[?contains(Arn,'token.actions')].Arn" --output text)
aws cloudformation deploy --stack-name fernslop-ecr --template-file infra/ecr-stack.yaml \
  --capabilities CAPABILITY_IAM --parameter-overrides ExistingOidcProviderArn="$PROVIDER"
```

(If the account already had a GitHub OIDC provider before `fernslop-github`, create that stack with `--parameter-overrides CreateOidcProvider=false ExistingOidcProviderArn=<arn>`.)

**2. GitHub variables.** Read the outputs, then set them:

```sh
aws cloudformation describe-stacks --stack-name fernslop-github --query "Stacks[0].Outputs" --output table
aws cloudformation describe-stacks --stack-name fernslop-ecr --query "Stacks[0].Outputs" --output table

gh variable set AWS_REGION --body eu-west-2
gh variable set ECR_PUSH_ROLE_ARN --body <EcrPushRoleArn>
gh variable set ECR_REPOSITORY_URI --body <RepositoryUri>

gh api -X PUT repos/Dakini/fernslop/environments/development     # creates the environment
gh variable set AWS_DEPLOY_ROLE_ARN --env development --body <DevelopmentDeployRoleArn>
```

**3. Build an image.** Push to `main` (or re-run CI). `build-and-push` puts the image in ECR. `deploy-dev` fails because there is no server yet; that is expected. Get the tag:

```sh
TAG=$(aws ecr describe-images --repository-name fernslop \
  --query "sort_by(imageDetails,&imagePushedAt)[-1].imageTags[0]" --output text)
```

**4. Create the server.** Pick one:

```sh
ALLOW_PLAIN_HTTP=true infra/deploy.sh dev "$TAG"             # http://<ip>, no domain
DOMAIN=fernslop.example.com infra/deploy.sh dev "$TAG"       # https; point the domain's DNS at the IP after
```

Add `EIP_ALLOCATION_ID=eipalloc-... EIP_ADDRESS=<ip>` to reuse an Elastic IP you already own, so the address survives deleting the stack (`aws ec2 describe-addresses` lists them). It waits until `/api/health` reports the tag.

**5. Point CI at the server.**

```sh
aws cloudformation describe-stacks --stack-name fernslop --query "Stacks[0].Outputs" --output table

gh variable set INSTANCE_ID --env development --body <InstanceId>
gh variable set DEPLOY_DOCUMENT --env development --body <DeployDocumentName>   # fernslop-deploy
gh variable set PUBLIC_URL --env development --body <Url>                       # no trailing path
```

Re-run the failed `deploy-dev` job. Done: every push to `main` now deploys to dev.

## If you delete the server

```sh
aws cloudformation delete-stack --stack-name fernslop
aws cloudformation wait stack-delete-complete --stack-name fernslop
```

A new server gets a new `INSTANCE_ID`, and a new `PUBLIC_URL` unless you reuse the Elastic IP: redo steps 4 and 5. Do not delete the other two stacks. The data on the server goes with it; there are no backups.

If the ECR repository was deleted by hand, delete the `fernslop-ecr` stack and redo step 1 for it, then update `ECR_PUSH_ROLE_ARN` and `ECR_REPOSITORY_URI`.

## Prod (only if you want it)

Same again with `prod`: `infra/deploy.sh prod "$TAG"` makes the stack `prod-fernslop`. Create the `production` environment, set `AWS_DEPLOY_ROLE_ARN` (`ProductionDeployRoleArn`), `INSTANCE_ID`, `DEPLOY_DOCUMENT` (`prod-fernslop-deploy`) and `PUBLIC_URL` on it, and limit its deployment branches to `main` in the GitHub settings. Then "Promote to prod" (Actions tab, `promote.yaml`) deploys the image dev is running. Use a different Elastic IP from dev's.

## How a deploy works

- `infra/build.sh` builds the arm64 image and pushes it to ECR as `<repo>:YYYYMMDD-HHMMSS-<sha>`. The tag is baked in, so `/api/health` reports it as `version`. There is no `:latest`. ECR keeps the last 50 tags.
- Each server stack has an SSM document `<stack name>-deploy` that takes a `tag`, sets `APP_TAG` in `/opt/app/.env` and runs `docker compose up -d --pull always`. CI sends that document; it does not use CloudFormation.
- `deploy-dev` waits until `/api/health` reports the new tag, smoke-tests `/` and `/api/plants`, then moves the `deployed-dev` git tag, which is what "Promote to prod" deploys. Nothing is rolled back on failure.
- `deploy.sh` creates the server stack on the first run. On later runs it updates the stack and sends the same SSM document. Rerun a failed `deploy-dev` with "Re-run failed jobs".
