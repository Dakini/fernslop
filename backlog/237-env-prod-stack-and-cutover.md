# [env] Create prod, move the data and switch the domain

## Goal

`infra/README.md` has a numbered cutover runbook the user follows by hand: prod is created and serves the live data on `fernslop.example.com`, and today's instance stays on as dev on `dev-fernslop.example.com`.

## Acceptance criteria

- [ ] Prod is created with the #234/#235 commands (prod env, an existing tag, `fernslop.example.com`). The runbook says the wait for `/api/health` in `deploy.sh` will fail because prod cannot get a certificate until the DNS switch, and gives an SSM check of the app's health on the instance itself.
- [ ] Freeze: stop `app` on dev before the final dump, so no writes are lost. Then run `fernslop-backup` once on dev, wait for it to succeed, and check the dump with `pg_restore --list`. The steps reuse the existing "Database backups" section rather than copying it.
- [ ] Restore that dump into prod (presigned link from dev's bucket). Then verify: on both instances, the per-table row counts in a shared query or helper script match, and one garden with a photo opens on prod.
- [ ] DNS (Cloudflare, DNS only / grey cloud): point the `fernslop` A record at prod's Elastic IP, wait for prod's certificate, and check `https://fernslop.example.com/api/health`. Then run one backup on prod and confirm it reaches prod's own bucket.
- [ ] Move dev: add a grey-cloud A record `dev-fernslop` → dev's Elastic IP. Edit `SITE_ADDRESS` in `/opt/app/caddy.env` and `FERNSLOP_PUBLIC_URL` in `/opt/app/app.env` by hand over SSM, restart `caddy` and `app`, and set dev's stack `DomainName` to match. Review the change set first and stop if it shows `Replacement: True`. Check `https://dev-fernslop.example.com/api/health`.
- [ ] Rollback is written at each step. Before the DNS switch: start `app` on dev again, and nothing is lost. After it: point DNS back and start dev's `app`, losing prod's writes since the switch. Dev's `app` must never start while the live domain still points at it.
- [ ] Every new or changed shell script passes `shellcheck`. The engineer runs nothing against AWS, and QA checks the runbook by reading it.

## Out of scope

- Anonymising dev's copy of the real data: [#241](parked/241-env-dev-data-scrub.md). Dev cannot email anyone today (no real sender, [#110](parked/110-api-email-sender.md)).
- Automating file changes on the running instance: [#208](parked/208-audit-apply-to-running-instance.md), parked.
- CI deploys and promotion: #238, #239.

## Constraints

- Only `infra/README.md`, plus at most one small read-only helper script in `infra/`. No app or template changes.
- Starts after #234, #235 and #236 are done. Use their stack names and commands, not today's hardcoded `fernslop`.
- Changing `DomainName` changes the user data, but user data runs only on first boot, so the hand edits are what actually move dev.
- Dev's domain stays one level deep (Cloudflare certificate limits). Prod's Caddy gets its certificate only after the switch.
