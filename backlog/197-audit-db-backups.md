# [audit] Nightly Postgres backups off the instance

## Goal

A nightly Postgres dump leaves the EC2 instance for an S3 bucket, a missing backup shows up in CloudWatch, and a restore procedure is written down and has been tried once (`audit.md` 1 backup bullet, 13 `pgdata` bullet).

## Acceptance criteria

- [ ] `infra/ec2-stack.yaml` adds an S3 bucket with default encryption, all public access blocked, `DeletionPolicy: Retain` (deleting the stack keeps the backups) and a lifecycle rule that expires dumps after 30 days.
- [ ] The instance role may only `s3:PutObject` under that bucket's backup prefix: no get, list or delete, so a compromised instance can neither read nor wipe old backups.
- [ ] A systemd timer on the instance (nightly, e.g. 03:00 UTC, `Persistent=true`) streams `pg_dump -Fc` from the compose `db` (`docker compose exec -T db`) to `s3://<bucket>/<prefix>/fernslop-<UTC timestamp>.dump` without writing the dump to the instance disk.
- [ ] Each successful backup publishes a CloudWatch metric; an alarm goes to ALARM when none has been recorded for 26 hours (missing data counts as breaching) and is shown on the `fernslop` dashboard.
- [ ] A short new `infra/README.md` says where the dumps are, how to download one with operator credentials, and how to restore it into the compose `db` (stop `app`, `pg_restore --clean`, start `app`).
- [ ] The restore was done once into a throwaway local `postgres:17-alpine` from a dump of `make up`, and the seed gardens plus one test garden were there afterwards; the issue comment says so.
- [ ] The template still validates (`aws cloudformation validate-template` or `cfn-lint`); no app code changes.

## Out of scope

- Getting the timer onto an already running instance: [#208](208-audit-apply-to-running-instance.md).
- Bringing back a single garden: use the 7-day soft delete from [#196](196-audit-garden-soft-delete.md).
- Photo bytes outside the database: [parked #205](parked/205-audit-photo-object-storage.md).

## Constraints

- `infra/ec2-stack.yaml`, new `infra/README.md`. The AWS CLI ships with Amazon Linux 2023.
- The dump holds follower emails and photos: keep it encrypted, never print it or its contents to logs.
- No tests (infrastructure); QA checks by reading the template and the restore note.
