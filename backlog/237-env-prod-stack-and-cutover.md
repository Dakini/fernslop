# [env] Create prod, move the data and switch the domain

## Goal

`infra/README.md` has a numbered cutover runbook the user follows by hand: prod is created and serves the live data on `fernslop.example.com`, and today's instance stays on as dev on `dev-fernslop.example.com`.

## Acceptance criteria

- [ ] Start: the dev one-time runbooks of [#234](done/234-env-parameterise-stacks.md), [#235](done/235-env-build-and-deploy-by-tag.md) and [#236](done/236-env-iam-split-per-environment.md) are done (linked, not copied). `TAG` is the tag dev runs now (`version` in its `/api/health`, built by `infra/build.sh`). `infra/deploy.sh prod --names` is checked, then `DOMAIN=fernslop.example.com infra/deploy.sh prod "$TAG"` creates prod with that `ImageTag`. It says the script's health wait will fail (no certificate until the DNS switch) and gives an SSM check of the app's health on the instance. The `production` GitHub values come from [#236's README step 5](../infra/README.md#one-time-replace-the-cloudformation-deploy-role-with-the-two-environment-roles), linked.
- [ ] Freeze and dump on dev: say not to push to `main` or promote meanwhile (a CI deploy would start `app` again). Stop `app`, then run `pg_dump -Fc` in the `db` container over SSM into a file only root can read. Check it with `pg_restore --list`. Dev has no `fernslop-backup`, backup bucket or alarm ([#234 engineer comment](done/234-env-parameterise-stacks.md)), so none are used.
- [ ] Transfer without new infrastructure: via prod's own backup bucket. The operator makes a 15-minute presigned PUT URL (`aws s3 presign` only does GET, so use `uvx --from boto3 python` for the PUT), dev uploads with `curl -T` to `db/cutover-<timestamp>.dump`, and the operator makes a GET link for prod. The file on dev, the bucket object and any local copy are deleted at the end (the dump holds emails and photos).
- [ ] Restore into prod with the existing [restore steps](../infra/README.md#restore-into-the-instances-compose-db) (linked, not copied). Then verify: the per-table row counts from a shared query or helper script match on dev and prod, and one garden with a photo opens on prod.
- [ ] DNS (Cloudflare, DNS only / grey cloud): point the `fernslop` A record at prod's Elastic IP, wait for the certificate, check `https://fernslop.example.com/api/health`. Then run one backup on prod and confirm the object is in prod's bucket and passes `pg_restore --list`. The first `promote.yaml` run comes only after this, and needs one successful `deploy-dev` first so `deployed-dev` exists ([#238](done/238-env-ci-build-and-deploy-dev.md), [#239](done/239-env-ci-promote-to-prod.md)).
- [ ] Move dev: add a grey-cloud A record `dev-fernslop` to dev's Elastic IP. Over SSM, edit `SITE_ADDRESS` in `/opt/app/caddy.env` and `FERNSLOP_PUBLIC_URL` in `/opt/app/app.env` (check which files the older instance has), restart `caddy`, start `app`, and set dev's stack `DomainName` to match. Review the change set first and stop if it shows `Replacement: True`. Check `https://dev-fernslop.example.com/api/health`.
- [ ] Rollback is written at each step. Before the DNS switch: start `app` on dev again, nothing is lost. After it: point DNS back and start dev's `app`, losing prod's writes since the switch. Dev's `app` must never start while the live domain still points at it.

## Out of scope

- Anonymising dev's copy of the real data: [#241](parked/241-env-dev-data-scrub.md). Dev cannot email anyone today (no real sender, [#110](parked/110-api-email-sender.md)).
- Automating file changes on the running instance: [#208](parked/208-audit-apply-to-running-instance.md), parked.

## Constraints

- Only `infra/README.md`, plus at most one small read-only helper script in `infra/` that passes `shellcheck`. No app or template changes. The engineer runs nothing against AWS; QA checks the runbook by reading it.
- Use the names and commands of the #234 to #236 README sections, not a hardcoded `fernslop`. Link to them instead of copying.
- Changing `DomainName` changes the user data, but user data runs only on first boot, so the hand edits are what actually move dev.
- Dev's domain stays one level deep (Cloudflare certificate limits). Prod's Caddy gets its certificate only after the switch.

**Orchestrator decision:** a short dev stop/start for the `DomainName` change is acceptable, since dev serves no users after the cutover. Still stop on `Replacement: True`.
