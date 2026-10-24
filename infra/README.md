# Infra

Fernslop runs on one EC2 instance (docker compose: `db`, `app`, `caddy`). Its CloudFormation stacks, set up once:

| Stack | Template | What it is |
| --- | --- | --- |
| `fernslop-github` | `github-oidc-stack.yaml` | GitHub OIDC login and the deploy roles CI uses |
| `fernslop-ecr` | `ecr-stack.yaml` | the image repository and the role CI uses to push |
| `fernslop` / `prod-fernslop` | `ec2-stack.yaml` | the dev and prod servers (made by `deploy.sh`) |
| `fernslop-obs` | `obs-stack.yaml` | the observability server both send telemetry to (made by `obs-deploy.sh`, optional) |

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

Dev, from the `fernslop` outputs:

```sh
gh variable set INSTANCE_ID --env development --body <InstanceId>
gh variable set DEPLOY_DOCUMENT --env development --body <DeployDocumentName>   # fernslop-deploy
gh variable set PUBLIC_URL --env development --body <Url>                       # https://<domain>, no trailing slash
```

Prod, from the `prod-fernslop` outputs:

```sh
gh variable set INSTANCE_ID --env production --body <InstanceId>
gh variable set DEPLOY_DOCUMENT --env production --body <DeployDocumentName>    # prod-fernslop-deploy
gh variable set PUBLIC_URL --env production --body <Url>                        # https://<domain>, no trailing slash
```

Re-run the failed `deploy-dev` job. Done: every push to `main` deploys to dev.

## Promote to prod

Prod only changes when you promote. Actions tab → "Promote to prod" (`promote.yaml`) → Run workflow, or `gh workflow run promote.yaml --ref main`. It deploys the image dev is running (the `deployed-dev` git tag), so it needs one successful `deploy-dev` first. The `production` environment's variables from steps 3 and 7 must be set.

## If you delete a server

```sh
aws cloudformation delete-stack --stack-name fernslop          # or prod-fernslop
aws cloudformation wait stack-delete-complete --stack-name fernslop
```

Redo step 6 with the same Elastic IP, then update `INSTANCE_ID` (step 7). Do not delete the two CI stacks. The database on the server goes with it. A nightly dump is kept in the stack's S3 backup bucket, which is not deleted with the stack, so only changes since the last dump are lost.

If the ECR repository was deleted by hand, stack updates fail with `repository ... does not exist`. Delete the `fernslop-ecr` stack, redo step 2 for it, then update `ECR_PUSH_ROLE_ARN` and `ECR_REPOSITORY_URI`.

## How a deploy works

The overview, from build to promotion, is in [`docs/deployment.md`](../docs/deployment.md#cicd-pipeline). The details:

- `infra/build.sh` builds the image. There is no `:latest` tag. ECR keeps the last 50 tags.
- Each server stack has an SSM document `<stack name>-deploy` that takes a `tag`, sets `APP_TAG` in `/opt/app/.env` and runs `docker compose up -d --pull always`. CI sends that document; it does not use CloudFormation.
- The deploy document also sets `FERNSLOP_ENVIRONMENT=<dev|prod>` in `/opt/app/app.env` from the stack's `Environment` parameter. The image itself is the same for dev and prod. The backend reports this, together with the image tag, on its OpenTelemetry traces (`backend/app/telemetry.py`).
- A server created before `FERNSLOP_ENVIRONMENT` existed only gets it after one `infra/deploy.sh <env> <tag>` run, which updates the deploy document. CI deploys after that keep it set.
- Traces, metrics and logs are only sent when the stack's `OtlpEndpoint` is set (see "Observability server" below). The deploy document then writes the `OTEL_*` variables into `app.env` on every deploy. It is empty by default.
- `deploy.sh` creates the server stack on the first run. On later runs it updates the stack and sends the same SSM document. Rerun a failed `deploy-dev` with "Re-run failed jobs".

## Observability server

Optional. One more small server, separate from the app servers, runs `observability/` (Collector, Tempo, Loki,
Prometheus, Grafana) behind Caddy on its own domain. Dev and prod both send it traces, metrics and logs. It costs
about $19 a month in `eu-west-2`: a t4g.small ($13), its public IP ($4) and a 20 GB disk ($2). Logs stay on its
disk, not CloudWatch. Telemetry is kept 7 days and is not backed up.

**1. Elastic IP and DNS.** Same as step 5 above:

```sh
aws ec2 allocate-address --domain vpc --tag-specifications 'ResourceType=elastic-ip,Tags=[{Key=Name,Value=fernslop-obs}]'
```

Point an A record for the domain (e.g. `obs.example.com`) at it. On Cloudflare: DNS only (grey cloud). Create it
before step 2 and before anything looks the name up. A lookup made before the record exists is cached as "not
found" for up to 30 minutes, by the app servers and Let's Encrypt too. Until then the apps log `NameResolutionError`
and their telemetry is dropped. If Caddy failed to get its certificate, it retries on its own, or restart it:
`docker restart fernslop-observability-caddy-1`.

**2. Create the server.**

```sh
DOMAIN=obs.example.com EIP_ALLOCATION_ID=<eipalloc-...> infra/obs-deploy.sh
```

The first run creates two SSM SecureStrings with random values: `/fernslop/otlp-token` (the app servers send it
with their telemetry) and `/fernslop/grafana-admin-password`. It waits until Grafana answers on `https://<domain>`.

**3. Log in to Grafana** at `https://<domain>` as `admin`, with:

```sh
aws ssm get-parameter --with-decryption --name /fernslop/grafana-admin-password --query Parameter.Value --output text
```

**4. Connect dev and prod.** Each takes the tag it is already running, so nothing new is released:

```sh
TAG=$(curl -s https://<dev domain>/api/health | jq -r .version)
OTLP_ENDPOINT=https://obs.example.com infra/deploy.sh dev "$TAG"
TAG=$(curl -s https://<prod domain>/api/health | jq -r .version)
OTLP_ENDPOINT=https://obs.example.com infra/deploy.sh prod "$TAG"
```

This updates each server stack, so its deploy document writes the `OTEL_*` variables. CI deploys keep them set
after that. `OTLP_ENDPOINT=` (empty) stops sending. An image built before the backend had OpenTelemetry sends nothing.

Grafana's dashboard has **Environment** (`dev`, `prod`) and **Deployed version** filters at the top.

**Change its configs.** Edit `observability/` and rerun `infra/obs-deploy.sh` (no variables needed). It uploads
the directory to the stack's S3 bucket, and the stack's SSM document `fernslop-obs-deploy` syncs it to the server
and restarts the stack. `observability/docker-compose.server.yaml` and `Caddyfile.server` are the server-only parts.

How it is reached:

- `https://<domain>/v1/traces`, `/v1/metrics`, `/v1/logs`: the Collector's OTLP HTTP. Caddy refuses a request
  without `Authorization: Bearer <otlp-token>` with 401.
- Everything else on `https://<domain>` is Grafana, with a login. Prometheus, Loki and Tempo are not reachable from
  outside.
- To change the token: `aws ssm put-parameter --overwrite` it, rerun `infra/obs-deploy.sh`, then redeploy dev and
  prod. Grafana reads the admin password only when it is first created; change it in Grafana after that.
- No SSH: `aws ssm start-session --target <InstanceId>`; the stack lives in `/opt/obs/observability`.
- Delete with `aws cloudformation delete-stack --stack-name fernslop-obs`. The Elastic IP and the two SSM
  parameters stay. Its telemetry goes with it.
