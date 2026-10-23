# [env] Build the image once by tag, and deploy only existing tags
**What:** A build script pushes the arm64 image tagged `YYYYMMDD-HHMMSS-shortsha` (UTC) to the shared, tag-immutable `fernslop` ECR repo, and `deploy.sh <env> <tag>` runs that tag on the instance, never builds, and records the deployed tag.
**Why:** The user wants build and deploy as separate stages, with dev and prod running specific tags instead of `:latest`.
**Edge cases:** The live dev compose file hardcodes `:latest`, so the switch needs a runbook step or [#208](parked/208-audit-apply-to-running-instance.md); the "keep last 10" ECR rule must not expire the tag prod runs.
