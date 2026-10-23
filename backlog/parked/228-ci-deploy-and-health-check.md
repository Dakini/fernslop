# [ci] Superseded: deploy from main and verify /api/health
**What:** Superseded by [#238](../238-env-ci-build-and-deploy-dev.md) (build, deploy to dev, verify) and [#239](../239-env-ci-promote-to-prod.md) (manual promotion to prod).
**Why:** The user split CI into build and deploy stages with a dev and a prod environment.
**Edge cases:** Main only, no overlapping deploys, region from `AWS_REGION`, no first deploy in CI, arm64 build, and no `environment:` on a job whose role trusts `refs/heads/main`.
