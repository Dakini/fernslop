# [audit] Apply stack file changes to the running instance

## Goal

`infra/deploy.sh` gets the current compose file, Caddyfile, backup script and systemd units onto an existing instance and restarts what changed, so changes like #195, #197, #198, #203 and #204 reach a running site without replacing the instance (EC2 user data runs only on first boot).

## Acceptance criteria

- [ ] Those files live once, as plain files under `infra/` (e.g. `infra/instance/`); the template no longer inlines them, and both a new stack and an update get them from there.
- [ ] On an existing stack, `deploy.sh` writes them to `/opt/app` and `/etc/systemd/system`, reloads systemd, enables the timers and runs `docker compose up -d`, so only changed services restart.
- [ ] The generated `.env` (Postgres password) is created only if missing and never regenerated; no secret appears in SSM command parameters, output or CloudWatch.
- [ ] The `pgdata` and `caddy_data` volumes survive: after a run the gardens are still there and Caddy keeps its certificate.
- [ ] The new files are validated first (`docker compose config`, `caddy validate`); on a failure nothing is replaced, the old setup keeps running and `deploy.sh` exits non-zero.
- [ ] On an existing stack `deploy.sh` runs a backup (#197) and waits for it before changing anything; a failed backup stops the deploy.
- [ ] Verified on a throwaway stack: create it, change the Caddyfile and a timer, re-run `deploy.sh`, both changes are live and a test garden is still there; `infra/README.md` says how it works.

## Out of scope

- None.

## Constraints

- `infra/deploy.sh`, `infra/ec2-stack.yaml`, new `infra/instance/`, `infra/README.md`. After #203 and #204 (they change the same files). No app code.

**Open questions (user):** (1) There is no live deployment whose data matters (2026-10-22), so replacing the instance works today: park this until there is, or do it now? (2) If now, may the engineer and QA create and delete a throwaway AWS stack to verify it (small cost)?
