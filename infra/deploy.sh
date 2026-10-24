#!/usr/bin/env bash
# Deploy an image tag that infra/build.sh already pushed to ECR: create the EC2 stack on the first deploy, or update
# it and run its SSM deploy document (<stack name>-deploy) after. Builds nothing and never touches the ECR stack.
# Usage: [DOMAIN=<domain>] infra/deploy.sh <dev|prod> <tag>   deploy that tag to that environment
#        infra/deploy.sh <dev|prod> --names                   print the resolved names; calls no AWS
# <tag> is what build.sh prints: YYYYMMDD-HHMMSS-<7-char sha>. It must be in ECR, and /api/health must report it
# once the deploy is done.
# APP_PREFIX (default fernslop, lowercase letters, digits and hyphens) names everything: dev uses <prefix>,
# prod uses prod-<prefix>, and both share the <prefix> ECR repo in the <prefix>-ecr stack.
# DOMAIN is only read on the first deploy (asked for if missing); on an existing stack it must match the
# stack's DomainName. ALLOW_PLAIN_HTTP=true creates a plain-HTTP stack with no domain.
# A first deploy boots <tag>. An update keeps the stack's ImageTag (what a replaced instance would boot) and
# runs the tag through the SSM document instead.
# EIP_ALLOCATION_ID=eipalloc-... and EIP_ADDRESS=<its IPv4 address> (both or neither) make a new stack use that
# existing Elastic IP instead of creating one (the stack's ExistingEipAllocationId and ExistingEipAddress). Like
# DOMAIN they apply only on the first deploy: an existing stack keeps what it has, and they are ignored with a note.
# The address is not looked up, so it must be the allocation's own. The IP stays outside the stack.
# CFN_ROLE_ARN=<arn> runs the stack updates as that CloudFormation service role.
# OTLP_ENDPOINT=https://<obs domain> sends the app's telemetry to the observability server (infra/obs-deploy.sh);
# OTLP_ENDPOINT= (set but empty) stops it. Unset keeps what the stack has.
set -euo pipefail

USAGE="Usage: [DOMAIN=<domain>] infra/deploy.sh <dev|prod> <tag>   (infra/deploy.sh <dev|prod> --names prints the names)"
TAG_PATTERN='^[0-9]{8}-[0-9]{6}-[0-9a-f]{7}$'

# 0. Names and arguments: no AWS calls before the tag is checked, so --names works without credentials
ENVIRONMENT="${1:-}"
case "$ENVIRONMENT" in
  dev | prod) ;;
  "") echo "Missing environment. $USAGE" >&2; exit 1 ;;
  *) echo "Unknown environment '$ENVIRONMENT': use dev or prod" >&2; exit 1 ;;
esac
PREFIX="${APP_PREFIX:-fernslop}"
if ! [[ "$PREFIX" =~ ^[a-z0-9-]+$ ]]; then
  echo "APP_PREFIX '$PREFIX' must be lowercase letters, digits and hyphens only" >&2
  exit 1
fi
if [ "$ENVIRONMENT" = prod ]; then NAME="prod-$PREFIX"; else NAME="$PREFIX"; fi
STACK="$NAME"            # ec2-stack.yaml; also the dashboard name and the instance's Name tag
ECR_STACK="$PREFIX-ecr"  # ecr-stack.yaml, shared by both environments; deployed by hand, never here
LOG_GROUP="/$NAME/app"
EIP_ALLOCATION_ID="${EIP_ALLOCATION_ID:-}"
EIP_ADDRESS="${EIP_ADDRESS:-}"
if [ -n "$EIP_ALLOCATION_ID$EIP_ADDRESS" ]; then
  # Same patterns as the template's parameters; checked before any AWS call
  if [ -z "$EIP_ALLOCATION_ID" ] || [ -z "$EIP_ADDRESS" ]; then
    echo "EIP_ALLOCATION_ID and EIP_ADDRESS go together: set both or neither" >&2
    exit 1
  fi
  if ! [[ "$EIP_ALLOCATION_ID" =~ ^eipalloc-[0-9a-f]+$ ]]; then
    echo "EIP_ALLOCATION_ID '$EIP_ALLOCATION_ID' must look like eipalloc-0123456789abcdef0" >&2
    exit 1
  fi
  OCTET='(25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9]?[0-9])'
  if ! [[ "$EIP_ADDRESS" =~ ^$OCTET\.$OCTET\.$OCTET\.$OCTET$ ]]; then
    echo "EIP_ADDRESS '$EIP_ADDRESS' must be an IPv4 address such as 203.0.113.10" >&2
    exit 1
  fi
fi

if [ "${2:-}" = "--names" ]; then
  cat <<EOF
environment  $ENVIRONMENT
stack        $STACK
ecr stack    $ECR_STACK
ecr repo     $PREFIX
log group    $LOG_GROUP
dashboard    $NAME
instance tag Name=$NAME
deploy doc   $STACK-deploy
EOF
  if [ -n "$EIP_ALLOCATION_ID" ]; then
    echo "elastic ip   $EIP_ADDRESS ($EIP_ALLOCATION_ID, existing; used when the stack is created)"
  else
    echo "elastic ip   created by the stack"
  fi
  exit 0
fi
TAG="${2:-}"
if [ -z "$TAG" ]; then echo "Missing tag. $USAGE" >&2; exit 1; fi
if ! [[ "$TAG" =~ $TAG_PATTERN ]]; then
  echo "Bad tag '$TAG': expected YYYYMMDD-HHMMSS-<7-char sha>, as infra/build.sh prints" >&2
  exit 1
fi
[ -z "${3:-}" ] || { echo "$USAGE" >&2; exit 1; }

cd "$(dirname "$0")/.."
REGION=$(aws configure get region)

default_network() { # sets VPC and SUBNET: the default VPC and its default subnet in <region>a
  VPC=$(aws ec2 describe-vpcs --filters Name=is-default,Values=true --query "Vpcs[0].VpcId" --output text)
  SUBNET=$(aws ec2 describe-subnets --filters Name=vpc-id,Values="$VPC" Name=default-for-az,Values=true \
    Name=availability-zone,Values="${REGION}a" --query "Subnets[0].SubnetId" --output text)
  if [ "$VPC" = None ] || [ "$SUBNET" = None ]; then
    echo "No default VPC with a default subnet in ${REGION}a; create one with: aws ec2 create-default-vpc" >&2
    exit 1
  fi
}
stack_output() { # <stack> <key>; empty when the stack has no such output
  local v
  v=$(aws cloudformation describe-stacks --stack-name "$1" \
    --query "Stacks[0].Outputs[?OutputKey=='$2'].OutputValue" --output text)
  [ "$v" = "None" ] && v=""
  echo "$v"
}
stack_param() { # <stack> <key>; empty when the stack has no such parameter or it is empty
  local v
  v=$(aws cloudformation describe-stacks --stack-name "$1" \
    --query "Stacks[0].Parameters[?ParameterKey=='$2'].ParameterValue" --output text)
  [ "$v" = "None" ] && v=""
  echo "$v"
}

# 1. The image must exist (read-only), before anything changes
if OUT=$(aws ecr describe-images --region "$REGION" --repository-name "$PREFIX" --image-ids "imageTag=$TAG" \
    --query 'imageDetails[0].imageTags' --output text 2>&1); then
  :
elif grep -q ImageNotFoundException <<<"$OUT"; then
  echo "Tag $TAG is not in ECR repository $PREFIX: run infra/build.sh at that commit first" >&2
  exit 1
else
  echo "Could not look up $PREFIX:$TAG in ECR: $OUT" >&2
  exit 1
fi

# 2. A domain is required (HTTPS) on the first deploy unless ALLOW_PLAIN_HTTP=true; an existing stack keeps its
# own, and must already take an ImageTag (infra/README.md, one-time steps).
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
  OLD_TAG=$(stack_param "$STACK" ImageTag)
  if [ -z "$OLD_TAG" ]; then
    echo "Stack $STACK has no ImageTag yet: run the one-time steps in infra/README.md (build and deploy by tag) first" >&2
    exit 1
  fi
  if [ -n "$EIP_ALLOCATION_ID" ]; then
    echo "Note: stack $STACK exists, so EIP_ALLOCATION_ID and EIP_ADDRESS are ignored (they apply only on creation)" >&2
  fi
elif [ -z "$DOMAIN_ARG" ] && [ "$PLAIN" != "true" ]; then
  read -r -p "Domain name for the site (served over HTTPS; you point its DNS at the instance after): " DOMAIN_ARG || true
  if [ -z "$DOMAIN_ARG" ]; then
    echo "A domain is required: DOMAIN=<domain> infra/deploy.sh $ENVIRONMENT $TAG." >&2
    echo "To run plain HTTP on the instance's IP instead (no TLS): ALLOW_PLAIN_HTTP=true infra/deploy.sh $ENVIRONMENT $TAG" >&2
    exit 1
  fi
fi

# 3. Instance: create it (it boots the tag) or update the stack and run the tag through the SSM document
# ${CFN_ROLE_ARN:+...} adds --role-arn only when CFN_ROLE_ARN is set
if [ "$STACK_EXISTS" = true ]; then
  # A stack created before a domain was required has none: keep it on plain HTTP rather than fail the update
  ALLOW=false
  [ -z "$OLD_DOMAIN" ] && ALLOW=true
  # Keep the running instance's AMI: LatestAmiId re-resolves on every update, and a newer image replaces the
  # instance. The stack's AmiId once set (no EC2 read needed), else the instance's own.
  AMI=$(stack_param "$STACK" AmiId)
  if [ -z "$AMI" ]; then
    AMI=$(aws ec2 describe-instances --instance-ids "$(stack_output "$STACK" InstanceId)" \
      --query "Reservations[0].Instances[0].ImageId" --output text)
  fi
  # ImageTag stays what it was: changing it would change the instance's UserData
  aws cloudformation deploy --stack-name "$STACK" --template-file infra/ec2-stack.yaml \
    --capabilities CAPABILITY_IAM --no-fail-on-empty-changeset \
    --parameter-overrides AppPrefix="$PREFIX" Environment="$ENVIRONMENT" AmiId="$AMI" AllowPlainHttp="$ALLOW" \
      ImageTag="$OLD_TAG" ${OTLP_ENDPOINT+OtlpEndpoint="$OTLP_ENDPOINT"} \
    ${CFN_ROLE_ARN:+--role-arn "$CFN_ROLE_ARN"}
  INSTANCE=$(stack_output "$STACK" InstanceId)
  DOCUMENT=$(stack_output "$STACK" DeployDocumentName)
  CMD=$(aws ssm send-command --instance-ids "$INSTANCE" --document-name "$DOCUMENT" --parameters "tag=$TAG" \
    --query Command.CommandId --output text)
  echo "Sent $DOCUMENT with tag=$TAG to $INSTANCE (command $CMD); waiting ..."
  # Not `aws ssm wait`: it gives up after 100 seconds, and a first pull can take longer
  STATUS=Pending
  ERRORS=0
  for _ in $(seq 360); do
    if STATUS=$(aws ssm get-command-invocation --command-id "$CMD" --instance-id "$INSTANCE" \
        --query Status --output text 2>/dev/null); then
      ERRORS=0
    else
      # The invocation can take a moment to appear after send-command
      STATUS=Pending
      ERRORS=$((ERRORS + 1))
      [ "$ERRORS" -lt 6 ] || { echo "Cannot read command $CMD's status on $INSTANCE" >&2; exit 1; }
    fi
    case "$STATUS" in Pending | InProgress | Delayed) sleep 5 ;; *) break ;; esac
  done
  if [ "$STATUS" != Success ]; then
    echo "Deploy document finished with status $STATUS; its output:" >&2
    aws ssm get-command-invocation --command-id "$CMD" --instance-id "$INSTANCE" \
      --query "[StandardOutputContent,StandardErrorContent]" --output text >&2 || true
    exit 1
  fi
else
  default_network
  aws cloudformation deploy --stack-name "$STACK" --template-file infra/ec2-stack.yaml \
    --capabilities CAPABILITY_IAM --no-fail-on-empty-changeset \
    --parameter-overrides AppPrefix="$PREFIX" Environment="$ENVIRONMENT" ImageTag="$TAG" \
      DomainName="$DOMAIN_ARG" AllowPlainHttp="$PLAIN" ${OTLP_ENDPOINT+OtlpEndpoint="$OTLP_ENDPOINT"} \
      ${EIP_ALLOCATION_ID:+ExistingEipAllocationId="$EIP_ALLOCATION_ID" ExistingEipAddress="$EIP_ADDRESS"} \
      VpcId="$VPC" SubnetId="$SUBNET" \
    ${CFN_ROLE_ARN:+--role-arn "$CFN_ROLE_ARN"}
fi

# 4. Done when /api/health reports the tag: a healthy old container does not count
URL=$(stack_output "$STACK" Url)
IP=$(stack_output "$STACK" ElasticIp)
SITE_DOMAIN=$(stack_param "$STACK" DomainName)
CURL=(curl -fsS -m 5)
if [ -n "$SITE_DOMAIN" ]; then
  echo "Create a DNS A record: $SITE_DOMAIN -> $IP (Cloudflare: DNS only / grey cloud, so Caddy can get its certificate)"
  # Reach the instance by IP before the record exists; the certificate only issues once DNS resolves
  CURL+=(--resolve "$SITE_DOMAIN:443:$IP")
fi
echo "Waiting for $URL/api/health to report $TAG ..."
BODY=""
for _ in $(seq 60); do
  if BODY=$("${CURL[@]}" "$URL/api/health" 2>/dev/null) && grep -Eq "\"version\" *: *\"$TAG\"" <<<"$BODY"; then
    echo "Deployed $TAG to $ENVIRONMENT: $URL"
    exit 0
  fi
  sleep 10
done
echo "Not reporting $TAG after 10 minutes (last /api/health: ${BODY:-no answer}); see the CloudWatch log group $LOG_GROUP (Caddy logs the certificate attempts)" >&2
exit 1
