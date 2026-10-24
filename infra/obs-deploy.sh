#!/usr/bin/env bash
# Create or update the observability server (infra/obs-stack.yaml, stack <prefix>-obs) and run its configs: sync
# observability/ to the stack's ConfigBucket, then send its SSM deploy document. Separate from the app servers.
# Usage: DOMAIN=<domain> EIP_ALLOCATION_ID=eipalloc-... infra/obs-deploy.sh   first run (creates the stack)
#        infra/obs-deploy.sh                                                   later runs (configs, template)
# The first run also creates the SSM SecureStrings /<prefix>/otlp-token and /<prefix>/grafana-admin-password
# with random values; an existing one is never overwritten. DOMAIN and EIP_ALLOCATION_ID apply only on creation.
# APP_PREFIX (default fernslop) as in infra/deploy.sh. CFN_ROLE_ARN=<arn> runs the stack change as that role.
set -euo pipefail

PREFIX="${APP_PREFIX:-fernslop}"
if ! [[ "$PREFIX" =~ ^[a-z0-9-]+$ ]]; then
  echo "APP_PREFIX '$PREFIX' must be lowercase letters, digits and hyphens only" >&2
  exit 1
fi
STACK="$PREFIX-obs"
cd "$(dirname "$0")/.."
REGION=$(aws configure get region)

stack_output() { # <key>
  local v
  v=$(aws cloudformation describe-stacks --stack-name "$STACK" \
    --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue" --output text)
  [ "$v" = "None" ] && v=""
  echo "$v"
}
stack_param() { # <key>
  local v
  v=$(aws cloudformation describe-stacks --stack-name "$STACK" \
    --query "Stacks[0].Parameters[?ParameterKey=='$1'].ParameterValue" --output text)
  [ "$v" = "None" ] && v=""
  echo "$v"
}

# 1. Secrets, generated once. The app servers read the token too (infra/ec2-stack.yaml).
for NAME in otlp-token grafana-admin-password; do
  if ! aws ssm get-parameter --name "/$PREFIX/$NAME" >/dev/null 2>&1; then
    aws ssm put-parameter --name "/$PREFIX/$NAME" --type SecureString --value "$(openssl rand -hex 32)" >/dev/null
    echo "Created SSM parameter /$PREFIX/$NAME"
  fi
done

# 2. The stack
if aws cloudformation describe-stacks --stack-name "$STACK" >/dev/null 2>&1; then
  AMI=$(stack_param AmiId)
  if [ -z "$AMI" ]; then
    AMI=$(aws ec2 describe-instances --instance-ids "$(stack_output InstanceId)" \
      --query "Reservations[0].Instances[0].ImageId" --output text)
  fi
  aws cloudformation deploy --stack-name "$STACK" --template-file infra/obs-stack.yaml \
    --capabilities CAPABILITY_IAM --no-fail-on-empty-changeset \
    --parameter-overrides AppPrefix="$PREFIX" AmiId="$AMI" \
    ${CFN_ROLE_ARN:+--role-arn "$CFN_ROLE_ARN"}
else
  if [ -z "${DOMAIN:-}" ] || [ -z "${EIP_ALLOCATION_ID:-}" ]; then
    echo "First run: DOMAIN=<domain> EIP_ALLOCATION_ID=eipalloc-... infra/obs-deploy.sh" >&2
    exit 1
  fi
  aws cloudformation deploy --stack-name "$STACK" --template-file infra/obs-stack.yaml \
    --capabilities CAPABILITY_IAM --no-fail-on-empty-changeset \
    --parameter-overrides AppPrefix="$PREFIX" DomainName="$DOMAIN" ExistingEipAllocationId="$EIP_ALLOCATION_ID" \
    ${CFN_ROLE_ARN:+--role-arn "$CFN_ROLE_ARN"}
fi
INSTANCE=$(stack_output InstanceId)
DOCUMENT=$(stack_output DeployDocumentName)
BUCKET=$(stack_output ConfigBucketName)
URL=$(stack_output Url)

# 3. Configs: the repo's observability/ directory is the only source
aws s3 sync --delete --only-show-errors --exclude README.md --exclude "*.DS_Store" observability/ "s3://$BUCKET/observability/"

# 4. Run them. A new instance needs a minute or two before SSM can reach it.
echo "Waiting for $INSTANCE to be reachable by SSM ..."
for _ in $(seq 60); do
  PING=$(aws ssm describe-instance-information --filters "Key=InstanceIds,Values=$INSTANCE" \
    --query "InstanceInformationList[0].PingStatus" --output text 2>/dev/null || true)
  [ "$PING" = Online ] && break
  sleep 10
done
[ "$PING" = Online ] || { echo "$INSTANCE is not online in SSM after 10 minutes" >&2; exit 1; }
CMD=$(aws ssm send-command --instance-ids "$INSTANCE" --document-name "$DOCUMENT" \
  --query Command.CommandId --output text)
echo "Sent $DOCUMENT to $INSTANCE (command $CMD); waiting ..."
STATUS=Pending
for _ in $(seq 360); do
  STATUS=$(aws ssm get-command-invocation --command-id "$CMD" --instance-id "$INSTANCE" \
    --query Status --output text 2>/dev/null || echo Pending)
  case "$STATUS" in Pending | InProgress | Delayed) sleep 5 ;; *) break ;; esac
done
if [ "$STATUS" != Success ]; then
  echo "Deploy document finished with status $STATUS; its output:" >&2
  aws ssm get-command-invocation --command-id "$CMD" --instance-id "$INSTANCE" \
    --query "[StandardOutputContent,StandardErrorContent]" --output text >&2 || true
  exit 1
fi

# 5. Done when Grafana answers through Caddy over HTTPS (the certificate needs the DNS record)
echo "Waiting for $URL/api/health ..."
for _ in $(seq 30); do
  if curl -fsS -m 5 "$URL/api/health" >/dev/null 2>&1; then
    echo "Observability is up: $URL (user admin, password: aws ssm get-parameter --with-decryption --name /$PREFIX/grafana-admin-password)"
    exit 0
  fi
  sleep 10
done
echo "$URL does not answer after 5 minutes: check its DNS A record points at the Elastic IP (Cloudflare: DNS only)" >&2
exit 1
