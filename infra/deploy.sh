#!/usr/bin/env bash
# Deploy Fernslop to AWS: ECR repo -> image -> EC2 stack (first time) or roll the instance forward (after).
# Usage: infra/deploy.sh [domain]   (default AWS credentials and region; the optional domain is only read on the first deploy)
set -euo pipefail

cd "$(dirname "$0")/.."
TAG=$(git rev-parse --short HEAD)
REGION=$(aws configure get region)
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
REGISTRY="$ACCOUNT.dkr.ecr.$REGION.amazonaws.com"

stack_output() { # <stack> <key>
  aws cloudformation describe-stacks --stack-name "$1" \
    --query "Stacks[0].Outputs[?OutputKey=='$2'].OutputValue" --output text
}

# 1. Registry
aws cloudformation deploy --stack-name fernslop-ecr --template-file infra/ecr-stack.yaml --no-fail-on-empty-changeset
REPO=$(stack_output fernslop-ecr RepositoryUri)

# 2. Image (the instance is ARM). :latest is what the instance's compose file runs.
aws ecr get-login-password | docker login --username AWS --password-stdin "$REGISTRY"
docker buildx build --platform linux/arm64 --push -t "$REPO:$TAG" -t "$REPO:latest" .

# 3. Instance: create it (it pulls :latest on boot) or tell the running one to pull and restart
if aws cloudformation describe-stacks --stack-name fernslop >/dev/null 2>&1; then
  aws cloudformation deploy --stack-name fernslop --template-file infra/ec2-stack.yaml \
    --capabilities CAPABILITY_IAM --no-fail-on-empty-changeset
  INSTANCE=$(stack_output fernslop InstanceId)
  CMD=$(aws ssm send-command --instance-ids "$INSTANCE" --document-name AWS-RunShellScript \
    --parameters 'commands=["set -e","cd /opt/app",
      "aws ecr get-login-password --region '"$REGION"' | docker login --username AWS --password-stdin '"$REGISTRY"'",
      "docker compose up -d --pull always","docker image prune -f"]' \
    --query Command.CommandId --output text)
  aws ssm wait command-executed --command-id "$CMD" --instance-id "$INSTANCE"
else
  aws cloudformation deploy --stack-name fernslop --template-file infra/ec2-stack.yaml \
    --capabilities CAPABILITY_IAM --no-fail-on-empty-changeset \
    --parameter-overrides DomainName="${1:-}"
fi

URL=$(stack_output fernslop Url)
IP=$(stack_output fernslop ElasticIp)
DOMAIN=$(aws cloudformation describe-stacks --stack-name fernslop \
  --query "Stacks[0].Parameters[?ParameterKey=='DomainName'].ParameterValue" --output text)
CURL=(curl -fsS -m 5)
if [ -n "$DOMAIN" ]; then
  echo "Create a DNS A record: $DOMAIN -> $IP (Cloudflare: DNS only / grey cloud, so Caddy can get its certificate)"
  # Reach the instance by IP before the record exists; the certificate only issues once DNS resolves
  CURL+=(--resolve "$DOMAIN:443:$IP")
fi
echo "Waiting for $URL/api/health ..."
for _ in $(seq 60); do
  "${CURL[@]}" "$URL/api/health" >/dev/null 2>&1 && { echo "Deployed $TAG: $URL"; exit 0; }
  sleep 10
done
echo "Not healthy after 10 minutes; see the CloudWatch log group /fernslop/app (Caddy logs the certificate attempts)" >&2
exit 1
