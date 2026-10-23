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

## Comments

**Engineer:** Implemented. Nothing was deployed and no AWS resources were created. All changes are additive, in `infra/ec2-stack.yaml` and the new `infra/README.md`. No app code changed.

What I did:
- `BackupBucket`: SSE-S3 default encryption, all four public-access blocks, `BucketOwnerEnforced`, `DeletionPolicy`/`UpdateReplacePolicy: Retain`, and a lifecycle rule on `db/` that expires dumps after 30 days and aborts unfinished multipart uploads after 1 day. `BackupBucketPolicy` also denies non-TLS requests.
- The instance role has a new `write-db-backups` policy: `s3:PutObject` on `${BackupBucket.Arn}/db/*` only, with no get, list or delete. It also allows `cloudwatch:PutMetricData`, limited to the `Fernslop` namespace. PutObject covers the multipart upload a streamed `aws s3 cp -` makes.
- User data has a new `=== db backups ===` block. It writes `/usr/local/bin/fernslop-backup`, which runs `docker compose exec -T db pg_dump -Fc` piped to `aws s3 cp - s3://<bucket>/db/fernslop-<UTC>.dump`. With `pipefail`, the metric is only sent if both sides succeed. The block also writes `fernslop-backup.service` (oneshot) and `fernslop-backup.timer` (`OnCalendar=*-*-* 03:00:00 UTC`, `Persistent=true`, enabled). The script never writes the dump to disk or logs it; it only logs the object key.
- `BackupMissingAlarm` watches `Fernslop/BackupSucceeded` (Sum per hour, 26 of 26 periods, `< 1`, `TreatMissingData: breaching`), so it goes to ALARM after 26 hours without a backup. The `fernslop` dashboard has two new widgets in the empty slot at x=12, y=6: the alarm's status and a per-day count of backups. There is a new `BackupBucketName` output.
- `infra/README.md` covers where the dumps are, how to download one with operator credentials (`aws s3 ls/cp`, plus a `pg_restore --list` check), and the restore. Because the instance can't read the bucket, the restore uses a presigned URL piped into `pg_restore --clean --if-exists --no-owner --single-transaction`, between `docker compose stop app` and `docker compose start app`.

How I verified:
- `uvx cfn-lint infra/ec2-stack.yaml` exits 0. I also rendered the `!Sub` strings locally: the dashboard body parses as JSON, and `bash -n` passes on the user data and the backup script.
- I ran the backup script rendered from the template against a throwaway copy of the `make up` stack (compose project `fernslop-b197`, port 55498; the user's stack on :8000 was not touched). That copy had the 3 seed gardens plus a test garden, "Backup test garden 197". A local `aws` shim stood in for S3 and CloudWatch. The dump streamed through the pipe (24 KB custom format), then the metric call ran.
- I restored that dump into a throwaway `postgres:17-alpine` (`fernslop-pg197`). It had all 8 tables, and `rooms` held Elm Street Allotment, Balcony Jungle, Orchard Corner and Backup test garden 197.
- I also ran the README's in-place procedure against the compose `db`. I added a garden after the dump, then stopped `app`, ran `pg_restore --clean`, and started `app`. `/api/rooms` then listed exactly the 3 seed gardens plus the test garden, and the later garden was gone.
- Failure path: with `db` stopped, the script exits 1 and makes no `put-metric-data` call. Both throwaway stacks and the local dump files were removed afterwards.

What could not be checked without deploying:
- That the stack creates and the instance role really can't get, list or delete (only the template was read and linted).
- That `aws s3 cp -` succeeds with PutObject alone on AL2023's CLI.
- That the timer fires at 03:00 UTC.
- That the metric lands and the alarm leaves ALARM after the first backup and returns to ALARM 26 hours later.
- That the dashboard widgets render.
- The presigned-URL download on the instance.

Note: when `pg_dump` fails, the streamed upload can still leave an empty or truncated object, because the instance can't delete it. No metric is sent in that case, and the README says to check a dump with `pg_restore --list` before relying on it. The stack's `Description` still says the data is lost when the instance is replaced. I left it alone to avoid a merge conflict with #203; it can be reworded once that lands.

**QA:**

## QA: PASS

- [x] S3 bucket with default encryption, all public access blocked, `DeletionPolicy: Retain`, 30-day expiry - PASS
      Read `BackupBucket`: SSE-S3 (AES256), all 4 public access blocks, `DeletionPolicy` and `UpdateReplacePolicy: Retain`, lifecycle `expire-db-dumps` on `db/` with `ExpirationInDays: 30` (plus abort incomplete multipart after 1 day). `BackupBucketPolicy` denies non-TLS access.
- [x] Instance role may only `s3:PutObject` under the backup prefix - PASS
      `write-db-backups` grants `s3:PutObject` on `${BackupBucket.Arn}/db/*` only. No other policy in the role mentions S3 or the bucket, so there is no get, list or delete. The second statement is `cloudwatch:PutMetricData` limited by the `cloudwatch:namespace = Fernslop` condition.
- [x] systemd timer (03:00 UTC, `Persistent=true`) streams `pg_dump -Fc` via `docker compose exec -T db` to `s3://<bucket>/db/fernslop-<UTC>.dump` without touching disk - PASS
      The unit and timer in user data are `OnCalendar=*-*-* 03:00:00 UTC`, `Persistent=true`, enabled with `--now`. I extracted the script from the template, substituted the bucket and region, and ran it against a throwaway compose project (`fernslop-qa197`, port 55597) with a fake `aws` on PATH. It piped a 24.6 KB custom-format dump into `aws s3 cp - s3://qa-bucket/db/fernslop-20261023T001004Z.dump`, then called `put-metric-data`, exited 0 and logged only the object key.
- [x] Each successful backup publishes a metric; alarm goes to ALARM after 26 hours without one (missing = breaching) and is on the dashboard - PASS
      `BackupMissingAlarm`: `Fernslop/BackupSucceeded`, Sum, 3600 s x 26/26, `< 1`, `TreatMissingData: breaching`. The script publishes the metric without dimensions, and the alarm has none, so they match. A 26 h evaluation range with a 1 h period is within CloudWatch's 7-day limit for periods of at least 1 h. The dashboard has an alarm widget and a per-day count widget. Failure path: with `db` stopped, the script exits 1 and makes no `put-metric-data` call. With `aws s3 cp` failing, it also exits 1 with no metric call (pipefail).
- [x] `infra/README.md` covers where the dumps are, the download with operator credentials and the restore (stop `app`, `pg_restore --clean`, start `app`) - PASS
      All three are present. I followed the in-place steps on the throwaway compose stack: added "After dump garden", ran `docker compose stop app`, then `pg_restore --clean --if-exists --no-owner --single-transaction` from the dump (exit 0), then `docker compose start app`. `/api/health` returned ok and `/api/rooms` listed exactly the 3 seed gardens plus "QA garden 197". The later garden was gone.
- [x] Restore done once into a throwaway `postgres:17-alpine` with the seed gardens plus a test garden, and noted in the issue comment - PASS
      The engineer comment says so. I repeated it: `pg_restore --list` reported "dump is readable", the restore exited 0, there were 8 public tables, and `rooms` held Elm Street Allotment, Balcony Jungle, Orchard Corner and QA garden 197.
- [x] Template validates; no app code changes - PASS
      `uvx cfn-lint infra/ec2-stack.yaml` exits 0. The #197 commits (`c15615b..HEAD`) touch only `infra/ec2-stack.yaml`, `infra/README.md` and this issue.

Tests: none, because this is infrastructure. `uvx cfn-lint infra/ec2-stack.yaml` exits 0. I ran the backup script, the restore and both failure paths by hand as described above. All throwaway containers, volumes and the image were removed, and the stack on :8000 was not touched.

Not checked (needs a deploy): real stack creation and IAM enforcement, `aws s3 cp -` multipart upload with PutObject only on AL2023, the timer firing, alarm state changes, dashboard rendering and the presigned-URL download on the instance. As noted, a failed dump can leave an empty object (I saw a 0-byte object when `db` was down). It sends no metric and the README says to check dumps with `pg_restore --list`.
