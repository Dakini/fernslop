# [env] CI: build on push to main, deploy to dev and verify
**What:** After the tests pass on `main`, a build job pushes the image (#235) and a deploy job deploys that tag to dev and checks `/api/health` plus a smoke test.
**Why:** The user wants every push built once and verified on dev; this supersedes [#228](parked/228-ci-deploy-and-health-check.md).
**Edge cases:** Keep #228's edge cases; the smoke test writes to dev's real-data copy and can hit the per-IP limits; health cannot prove the new image until [#229](parked/229-ci-deploy-version-check.md).
