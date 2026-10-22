# [audit] Follow-up: apply stack file changes to the running instance
**What:** Make `infra/deploy.sh`, for an existing stack, write the current compose file, Caddyfile, env files and systemd timers to `/opt/app` on the running instance (e.g. through SSM) and restart what changed, instead of relying on EC2 user data, which only runs on first boot.
**Why:** Found while grooming #195, #197, #198, #203 and #204: all change files the user-data script writes, and a CloudFormation update to `UserData` does not re-run it on the existing instance, so none of them would reach the deployed site short of replacing the instance, which loses the database.
**Edge cases:** Keep the generated Postgres password, never regenerate it; no secret in SSM command history or CloudWatch; Caddy's certificate volume survives; one source of truth for the files (e.g. move them from the template into `infra/`); a failed step leaves the old setup running; take a backup (#197) before the first run.

**User decision (2026-10-22):** there is no live deployment whose data matters, so the infra issues (195, 197, 198, 203, 204) can be verified on the template or a fresh stack and do not wait for this issue.
