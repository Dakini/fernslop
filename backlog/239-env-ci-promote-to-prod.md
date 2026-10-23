# [env] CI: manual workflow that promotes dev's image to prod
**What:** A `workflow_dispatch` workflow reads dev's recorded tag, deploys that exact tag to prod without building, and checks prod's `/api/health`.
**Why:** The user wants prod promotion to be manual and to run exactly what dev runs.
**Edge cases:** Refuse if dev has no recorded tag, is unhealthy, or the run is not on `main`; no schema migrations yet ([#140](parked/140-db-migrations.md)); tag check is [#229](229-ci-deploy-version-check.md); rollback is [#230](parked/230-ci-deploy-rollback.md).
