#!/usr/bin/env bash
# Deploy Fernslop to AWS: ECR repo -> image -> EC2 stack (first time) or roll the instance forward (after).
# Usage: [DOMAIN=<domain>] infra/deploy.sh <dev|prod>     deploy that environment
#        infra/deploy.sh <dev|prod> --names               print the resolved names; calls no AWS
# APP_PREFIX (default fernslop, lowercase letters, digits and hyphens) names everything: dev uses <prefix>,
# prod uses prod-<prefix>, and both share the <prefix> ECR repo in the <prefix>-ecr stack.
# DOMAIN is only read on the first deploy (asked for if missing); on an existing stack it must match the
# stack's DomainName. ALLOW_PLAIN_HTTP=true creates a plain-HTTP stack with no domain.
# CFN_ROLE_ARN=<arn> runs the stack updates as that CloudFormation service role: CI, infra/github-oidc-stack.yaml.
set -euo pipefail

usage() { echo "Usage: [DOMAIN=<domain>] infra/deploy.sh <dev|prod> [--names]" >&2; exit 1; }

# 0. Names: no AWS calls before this point, so --names works without credentials
ENVIRONMENT="${1:-}"
case "$ENVIRONMENT" in
  dev | prod) ;;
  "") echo "Missing environment. Usage: [DOMAIN=<domain>] infra/deploy.sh <dev|prod> [--names]" >&2; exit 1 ;;
  *) echo "Unknown environment '$ENVIRONMENT': use dev or prod" >&2; exit 1 ;;
esac
PREFIX="${APP_PREFIX:-fernslop}"
if ! [[ "$PREFIX" =~ ^[a-z0-9-]+$ ]]; then
  echo "APP_PREFIX '$PREFIX' must be lowercase letters, digits and hyphens only" >&2
  exit 1
fi
if [ "$ENVIRONMENT" = prod ]; then NAME="prod-$PREFIX"; else NAME="$PREFIX"; fi
STACK="$NAME"            # ec2-stack.yaml; also the dashboard name and the instance's Name tag
ECR_STACK="$PREFIX-ecr"  # ecr-stack.yaml, shared by both environments
LOG_GROUP="/$NAME/app"

if [ "${2:-}" = "--names" ]; then
  cat <<EOF
environment  $ENVIRONMENT
stack        $STACK
ecr stack    $ECR_STACK
ecr repo     $PREFIX
log group    $LOG_GROUP
dashboard    $NAME
instance tag Name=$NAME
EOF
  exit 0
fi
[ -z "${2:-}" ] || usage

cd "$(dirname "$0")/.."
TAG=$(git rev-parse --short HEAD)
REGION=$(aws configure get region)
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
REGISTRY="$ACCOUNT.dkr.ecr.$REGION.amazonaws.com"

stack_output() { # <stack> <key>
  aws cloudformation describe-stacks --stack-name "$1" \
    --query "Stacks[0].Outputs[?OutputKey=='$2'].OutputValue" --output text
}
stack_param() { # <stack> <key>; empty when the stack has no such parameter or it is empty
  local v
  v=$(aws cloudformation describe-stacks --stack-name "$1" \
    --query "Stacks[0].Parameters[?ParameterKey=='$2'].ParameterValue" --output text)
  [ "$v" = "None" ] && v=""
  echo "$v"
}

# 1. A domain is required (HTTPS) on the first deploy unless ALLOW_PLAIN_HTTP=true; an existing stack keeps its
# own. Checked before the build.
STACK_EXISTS=false
aws cloudformation describe-stacks --stack-name "$STACK" >/dev/null 2>&1 && STACK_EXISTS=true
DOMAIN_ARG="${DOMAIN:-}"
PLAIN="${ALLOW_PLAIN_HTTP:-false}"
if [ "$STACK_EXISTS" = true ]; then
  OLD_DOMAIN=$(stack_param "$STACK" DomainName)
  if [ -n "$DOMAIN_ARG" ] && [ "$DOMAIN_ARG" != "$OLD_DOMAIN" ]; then
    echo "DOMAIN=$DOMAIN_ARG differs from stack $STACK's DomainName '$OLD_DOMAIN'; a domain change is a manual cutover, not a deploy" >&2
    exit 1
  fi
elif [ -z "$DOMAIN_ARG" ] && [ "$PLAIN" != "true" ]; then
  read -r -p "Domain name for the site (served over HTTPS; you point its DNS at the instance after): " DOMAIN_ARG || true
  if [ -z "$DOMAIN_ARG" ]; then
    echo "A domain is required: DOMAIN=<domain> infra/deploy.sh $ENVIRONMENT." >&2
    echo "To run plain HTTP on the instance's IP instead (no TLS): ALLOW_PLAIN_HTTP=true infra/deploy.sh $ENVIRONMENT" >&2
    exit 1
  fi
fi

# 2. Registry (shared by dev and prod)
# ${CFN_ROLE_ARN:+...} adds --role-arn only when CFN_ROLE_ARN is set; operator deploys are unchanged
aws cloudformation deploy --stack-name "$ECR_STACK" --template-file infra/ecr-stack.yaml --no-fail-on-empty-changeset \
  --parameter-overrides AppPrefix="$PREFIX" \
  ${CFN_ROLE_ARN:+--role-arn "$CFN_ROLE_ARN"}
REPO=$(stack_output "$ECR_STACK" RepositoryUri)

# 3. Image (the instance is ARM). :latest is what the instance's compose file runs.
aws ecr get-login-password | docker login --username AWS --password-stdin "$REGISTRY"
docker buildx build --platform linux/arm64 --push -t "$REPO:$TAG" -t "$REPO:latest" .

# 4. Instance: create it (it pulls :latest on boot) or tell the running one to pull and restart
if [ "$STACK_EXISTS" = true ]; then
  # A stack created before a domain was required has none: keep it on plain HTTP rather than fail the update
  ALLOW=false
  [ -z "$OLD_DOMAIN" ] && ALLOW=true
  # Keep the running instance's AMI: LatestAmiId re-resolves on every update, and a newer image replaces the
  # instance. The stack's AmiId once set (no EC2 read needed, so CI can deploy), else the instance's own.
  AMI=$(stack_param "$STACK" AmiId)
  if [ -z "$AMI" ]; then
    AMI=$(aws ec2 describe-instances --instance-ids "$(stack_output "$STACK" InstanceId)" \
      --query "Reservations[0].Instances[0].ImageId" --output text)
  fi
  aws cloudformation deploy --stack-name "$STACK" --template-file infra/ec2-stack.yaml \
    --capabilities CAPABILITY_IAM --no-fail-on-empty-changeset \
    --parameter-overrides AppPrefix="$PREFIX" Environment="$ENVIRONMENT" AmiId="$AMI" AllowPlainHttp="$ALLOW" \
    ${CFN_ROLE_ARN:+--role-arn "$CFN_ROLE_ARN"}
  INSTANCE=$(stack_output "$STACK" InstanceId)
  CMD=$(aws ssm send-command --instance-ids "$INSTANCE" --document-name AWS-RunShellScript \
    --parameters 'commands=["set -e","cd /opt/app",
      "aws ecr get-login-password --region '"$REGION"' | docker login --username AWS --password-stdin '"$REGISTRY"'",
      "docker compose up -d --pull always","docker image prune -f"]' \
    --query Command.CommandId --output text)
  aws ssm wait command-executed --command-id "$CMD" --instance-id "$INSTANCE"
else
  aws cloudformation deploy --stack-name "$STACK" --template-file infra/ec2-stack.yaml \
    --capabilities CAPABILITY_IAM --no-fail-on-empty-changeset \
    --parameter-overrides AppPrefix="$PREFIX" Environment="$ENVIRONMENT" \
      DomainName="$DOMAIN_ARG" AllowPlainHttp="$PLAIN" \
    ${CFN_ROLE_ARN:+--role-arn "$CFN_ROLE_ARN"}
fi

URL=$(stack_output "$STACK" Url)
IP=$(stack_output "$STACK" ElasticIp)
SITE_DOMAIN=$(stack_param "$STACK" DomainName)
CURL=(curl -fsS -m 5)
if [ -n "$SITE_DOMAIN" ]; then
  echo "Create a DNS A record: $SITE_DOMAIN -> $IP (Cloudflare: DNS only / grey cloud, so Caddy can get its certificate)"
  # Reach the instance by IP before the record exists; the certificate only issues once DNS resolves
  CURL+=(--resolve "$SITE_DOMAIN:443:$IP")
fi
echo "Waiting for $URL/api/health ..."
for _ in $(seq 60); do
  "${CURL[@]}" "$URL/api/health" >/dev/null 2>&1 && { echo "Deployed $TAG to $ENVIRONMENT: $URL"; exit 0; }
  sleep 10
done
echo "Not healthy after 10 minutes; see the CloudWatch log group $LOG_GROUP (Caddy logs the certificate attempts)" >&2
exit 1
