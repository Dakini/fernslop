# [ci] Follow-up: health check proves the newly deployed version is running
**What:** Expose the deployed commit (e.g. a `version` field in `/api/health` or a build-arg baked into the image) and have the CI health check (#228) require it to equal the commit being deployed.
**Why:** Moved out of [#228](../228-ci-deploy-and-health-check.md): the instance runs `:latest`, so a 200 from `/api/health` cannot tell the new container from an old one that kept running.
**Edge cases:** Do not leak more than a short commit SHA; `/api/health` is unauthenticated and never rate-limited (`backend/app/test_rate_limit.py`); local and e2e builds have no commit, so the field must be optional.
