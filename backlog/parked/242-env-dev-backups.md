# [env] Follow-up: nightly backups on the dev instance
**What:** Install the backup bucket, script and alarm on dev by rebuilding it from the repo's template.
**Why:** Dev's live stack predates backups (see [#234](../done/234-env-parameterise-stacks.md)), so after the cutover it has none.
**Edge cases:** Rebuilding replaces the instance and loses dev's data; do it after the cutover ([#237](../237-env-prod-stack-and-cutover.md)) and ideally with [#241](241-env-dev-data-scrub.md), since dev holds a copy of real data.
