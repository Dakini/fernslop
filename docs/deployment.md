# Deployment

How Fernslop is deployed, and how changes reach dev and prod.

## Live environments

| Environment | URL | Updated |
| --- | --- | --- |
| Production | <URL> | By hand, with the "Promote to prod" workflow |
| Development | <URL> | On every push to `main` |
| Grafana (observability) | <URL> | When `observability/` changes (login needed) |

## Hosting

Each environment is one small AWS EC2 server (arm64) in `eu-west-2`. It runs Docker Compose with three containers:

- `caddy`: HTTPS, with certificates from Let's Encrypt
- `app`: the Fernslop image, pulled from ECR
- `db`: PostgreSQL

Everything is defined in CloudFormation templates in [`infra/`](../infra/):

| Stack | Template | What it is |
| --- | --- | --- |
| `fernslop-github` | `github-oidc-stack.yaml` | GitHub OIDC login and the deploy roles CI uses (no stored AWS keys) |
| `fernslop-ecr` | `ecr-stack.yaml` | The image registry and its push role |
| `fernslop` / `prod-fernslop` | `ec2-stack.yaml` | The dev and prod servers |
| `fernslop-obs` | `obs-stack.yaml` | The observability server (optional) |

## CI/CD pipeline

```
 pull request ──▶ backend tests ─┐
                  frontend tests ├──▶ (all must pass)
                  stack + e2e ───┘
                                       push to main also runs:
                                       ──▶ build arm64 image ──▶ push to ECR ──▶ deploy to dev ──▶ health + smoke check
                                                                                       │
                       "Promote to prod" (manual) ◀─────── deployed-dev tag ◀──────────┘
                              │
                              └──▶ deploy the same image to prod ──▶ health check
```

| Workflow | Trigger | Jobs |
| --- | --- | --- |
| [`ci.yaml`](../.github/workflows/ci.yaml) | Every pull request, and every push to `main` | `backend`, `frontend`, `stack` (Docker stack plus Playwright e2e). On `main` only: `build-and-push`, `deploy-dev` |
| [`promote.yaml`](../.github/workflows/promote.yaml) | Manual (Actions tab, or `gh workflow run promote.yaml --ref main`) | Deploys the image dev is running to prod |

How a deploy works:

1. `build-and-push` builds the image and tags it `YYYYMMDD-HHMMSS-<sha>`. The tag is baked in, and `/api/health` reports it as `version`.
2. `deploy-dev` sends an SSM command to the dev server. The server sets the new tag and runs `docker compose up -d --pull always`.
3. CI waits until `/api/health` reports the new tag, then smoke-tests `/` and `/api/plants`.
4. On success, the `deployed-dev` git tag moves to that commit. That is the image "Promote to prod" deploys, so prod only ever gets an image that already passed on dev.

Prod uses the same image as dev. Only the environment settings differ.

## Deploy your own copy

You need an AWS account, a GitHub fork, the `aws` and `gh` CLIs (logged in), and optionally two domain names.

The full step-by-step guide, with every command, is in [`infra/README.md`](../infra/README.md). In short:

1. Create the two CI stacks (`fernslop-github`, `fernslop-ecr`) with `aws cloudformation deploy`.
2. Set the GitHub repository and environment variables from their outputs (`development` and `production` environments).
3. Push to `main` once, so CI builds the first image.
4. Allocate an Elastic IP per server and point a DNS A record at each.
5. Create the servers: `infra/deploy.sh dev <tag>` and `infra/deploy.sh prod <tag>`.
6. Set each environment's `INSTANCE_ID`, `DEPLOY_DOCUMENT` and `PUBLIC_URL` variables in GitHub.
7. Re-run `deploy-dev`. From then on, every push to `main` deploys to dev.
8. Optional: create the observability server with `infra/obs-deploy.sh`, then point dev and prod at it.

Rerunning a step is safe: the scripts create a stack, or update it if it exists.

## Rollback

There is no automatic rollback. To go back, deploy an earlier tag (`infra/deploy.sh <env> <tag>`). ECR keeps the last 50 tags.
