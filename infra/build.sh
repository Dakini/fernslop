#!/usr/bin/env bash
# Build the app image once per commit and push it to ECR as <repo>:<tag>. Nothing else is pushed (no :latest).
# Usage: infra/build.sh                 build and push HEAD (a clean tree), unless the tag is already in ECR
#        infra/build.sh --print-tag     print HEAD's tag; calls neither AWS nor docker
# The tag is YYYYMMDD-HHMMSS-<7-char sha>: HEAD's committer time in UTC plus its short sha, so the same commit
# always gives the same tag. The last line on stdout is the tag; everything else goes to stderr, so
# TAG=$(infra/build.sh) works.
# APP_PREFIX (default fernslop) names the ECR repository. ECR_REPOSITORY_URI (the repository's full URI) skips the
# account lookup; CI sets it from a repository variable.
set -euo pipefail

cd "$(dirname "$0")/.."

# Committer time in UTC, the same on macOS and Linux (git formats it; no `date` flags involved)
TAG=$(TZ=UTC git show -s --date=format-local:%Y%m%d-%H%M%S --format=%cd HEAD)-$(git rev-parse --short=7 HEAD)

case "${1:-}" in
  --print-tag) echo "$TAG"; exit 0 ;;
  "") ;;
  *) echo "Usage: infra/build.sh [--print-tag]" >&2; exit 1 ;;
esac

PREFIX="${APP_PREFIX:-fernslop}"
if ! [[ "$PREFIX" =~ ^[a-z0-9-]+$ ]]; then
  echo "APP_PREFIX '$PREFIX' must be lowercase letters, digits and hyphens only" >&2
  exit 1
fi
if [ -n "$(git status --porcelain)" ]; then
  echo "The working tree is not clean: commit or stash first, so the image matches tag $TAG" >&2
  exit 1
fi

if [ -n "${ECR_REPOSITORY_URI:-}" ]; then
  REPO="$ECR_REPOSITORY_URI"
else
  REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-$(aws configure get region)}}"
  ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
  REPO="$ACCOUNT.dkr.ecr.$REGION.amazonaws.com/$PREFIX"
fi
REGISTRY="${REPO%%/*}"        # <account>.dkr.ecr.<region>.amazonaws.com
REPO_NAME="${REPO#*/}"
REGION="${REGISTRY#*.dkr.ecr.}"
REGION="${REGION%%.*}"

# Tags are immutable, so a second push of the same tag would fail: skip the build when it is already there
if OUT=$(aws ecr describe-images --region "$REGION" --repository-name "$REPO_NAME" \
    --image-ids "imageTag=$TAG" --query 'imageDetails[0].imageTags' --output text 2>&1); then
  echo "$REPO:$TAG is already in ECR; nothing to build" >&2
  echo "$TAG"
  exit 0
elif ! grep -q ImageNotFoundException <<<"$OUT"; then
  echo "Could not look up $REPO:$TAG in ECR: $OUT" >&2
  exit 1
fi

# docker's own output goes to stderr so that the tag stays the last line on stdout
aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$REGISTRY" >&2
# The instance is ARM. The tag is baked in so /api/health can report it (#229).
docker buildx build --platform linux/arm64 --push --build-arg "FERNSLOP_IMAGE_TAG=$TAG" -t "$REPO:$TAG" . >&2
echo "$TAG"
