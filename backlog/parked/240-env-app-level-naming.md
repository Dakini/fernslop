# [env] Follow-up: make app-level names configurable for forks
**What:** Decide whether forks need to rename the `FERNSLOP_*` env vars, the Postgres user/database and the UI brand.
**Why:** Moved out of [#234](../234-env-parameterise-stacks.md), which only parameterises AWS resources and the domain.
**Edge cases:** Renaming the database user breaks restores of existing dumps.
