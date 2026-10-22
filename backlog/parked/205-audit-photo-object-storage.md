# [audit] Follow-up: move photo bytes to object storage
**What:** Store photo bytes in object storage (e.g. S3) with a lifecycle rule for unposted uploads, instead of the `photos` table in Postgres.
**Why:** Moved out of #198; `audit.md` 2 lists it as the longer-term fix. It is an architecture change, and the disk ceiling and cleanup in #198 cover the immediate risk.
**Edge cases:** Existing photos need a migration path and photo URLs must stay stable; local dev without AWS; backups (#197) and soft-delete purge (#196) must cover the new store; public-read vs. signed URLs.
