# [env] Split the GitHub and CloudFormation roles per environment
**What:** Deploy `infra/github-oidc-stack.yaml` once per environment so each role reaches only its own environment's resources, taking items 1 and 3 from [#233](parked/233-ci-deploy-iam-hardening.md); the user applies it live.
**Why:** Both environments share one AWS account, so only IAM stops a dev deploy from touching prod.
**Edge cases:** The account has one OIDC provider; the prod role must trust the manual promotion via the `production` environment `sub`, which the dev role must not.
