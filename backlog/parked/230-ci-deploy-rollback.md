# [ci] Follow-up: roll back automatically when the post-deploy health check fails
**What:** When the CI health check (#228) fails, re-point the instance at the previous image tag (ECR keeps the last 10, `infra/ecr-stack.yaml`) and restart it, then report the deploy as failed.
**Why:** Moved out of [#228](228-ci-deploy-and-health-check.md), which only detects a bad deploy; today the instance compose file runs `:latest`, so rollback needs it to run a pinned tag first.
**Edge cases:** A database change made by the new version may not work with the old one (no migrations yet, [#140](140-db-migrations.md)); the rollback itself must be health-checked; never loop deploy/rollback.
