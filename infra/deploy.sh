#!/usr/bin/env bash
# Deploy Fernslop to AWS: create/update the CloudFormation stack, push the image, start the service.
# Usage: infra/deploy.sh   (uses the default AWS credentials and region)
set -euo pipefail

STACK=fernslop
TAG=$(git rev-parse --short HEAD)
cd "$(dirname "$0")/.."

REGION=$(aws configure get region)
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
REGISTRY="$ACCOUNT.dkr.ecr.$REGION.amazonaws.com"

deploy() { # <desired count>
  aws cloudformation deploy --stack-name "$STACK" --template-file infra/template.yaml \
    --capabilities CAPABILITY_IAM --no-fail-on-empty-changeset \
    --parameter-overrides ImageTag="$TAG" DesiredCount="$1"
}

output() {
  aws cloudformation describe-stacks --stack-name "$STACK" \
    --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue" --output text
}

# 1. Infrastructure. With no image pushed yet the service must not start, so keep it at 0.
if aws cloudformation describe-stacks --stack-name "$STACK" >/dev/null 2>&1; then
  COUNT=$(aws ecs describe-services --cluster "$(output ClusterName)" --services "$(output ServiceName)" \
    --query 'services[0].desiredCount' --output text)
else
  COUNT=0
fi
deploy "$COUNT"

# 2. Image (Fargate runs ARM64 here)
aws ecr get-login-password | docker login --username AWS --password-stdin "$REGISTRY"
docker buildx build --platform linux/arm64 --push -t "$(output RepositoryUri):$TAG" .

# 3. Run it
deploy 1
aws ecs wait services-stable --cluster "$(output ClusterName)" --services "$(output ServiceName)"
echo "Deployed $TAG: $(output Url)"
