# [ci] Follow-up: make the CI test jobs required status checks on main
**What:** In the GitHub repository settings (branch protection or a ruleset on `main`), require the `backend` and `frontend` checks from `.github/workflows/ci.yaml` (and later `stack`, #226) to pass before a PR can merge.
**Why:** Moved out of [#225](../225-ci-unit-tests-workflow.md): the workflow reports failures, but nothing stops a red PR being merged. This is a repository setting changed by the repo owner, not a file in the repo.
**Edge cases:** Required check names must match the job names exactly, so renaming a job silently un-requires it; decide whether admins may bypass.
