# [env] Follow-up: anonymise the real-data copy on dev
**What:** After the cutover, scrub follower emails and photos on dev or replace the data with seed data.
**Why:** Moved out of [#237](../237-env-prod-stack-and-cutover.md); dev gets every push and smoke test, so real PII there is exposed more widely.
**Edge cases:** Dev's backup bucket keeps real dumps for 30 days; a scrub must never run against prod.
