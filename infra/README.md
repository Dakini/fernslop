# Infra

`ec2-stack.yaml` runs Fernslop on one EC2 instance with docker compose (`db`, `app`, `caddy`) in `/opt/app`; `deploy.sh` creates or updates it.

## Database backups

Every night at 03:00 UTC (or at the next boot if the instance was off then) the `fernslop-backup.timer` systemd timer runs `/usr/local/bin/fernslop-backup`. That script streams `pg_dump -Fc` from the compose `db` straight to S3; the dump never lands on the instance's disk. It then records a `Fernslop/BackupSucceeded` metric.

- **Where:** `s3://<BackupBucketName>/db/fernslop-<UTC timestamp>.dump`, where `BackupBucketName` is a stack output. Objects are encrypted (SSE-S3), the bucket blocks all public access and refuses non-TLS requests, and dumps expire after 30 days. The bucket is kept when the stack is deleted.
- **Who can read them:** only operator credentials. The instance role can only write under `db/`, so it cannot list, read or delete earlier dumps.
- **Alarm:** `BackupMissingAlarm` goes to ALARM after 26 hours without a `BackupSucceeded` data point. The `fernslop` dashboard shows it next to a per-day count of backups. To see why a run failed, use `journalctl -u fernslop-backup` on the instance.
- **Run one now:** on the instance (SSM Session Manager), run `sudo systemctl start fernslop-backup`.

A failed run publishes no metric, but it can leave an empty or truncated object behind. Check a dump before you rely on it (below).

The dumps contain follower emails and photos. Keep downloaded copies off shared disks and delete them when you are done.

### Download a dump (operator credentials)

```sh
BUCKET=$(aws cloudformation describe-stacks --stack-name fernslop \
  --query "Stacks[0].Outputs[?OutputKey=='BackupBucketName'].OutputValue" --output text)
aws s3 ls "s3://$BUCKET/db/"                                   # newest name sorts last
aws s3 cp "s3://$BUCKET/db/fernslop-20261023T030000Z.dump" ./fernslop.dump
pg_restore --list ./fernslop.dump >/dev/null && echo "dump is readable"   # or run it in a postgres:17-alpine container
```

### Restore into the instance's compose `db`

The restore replaces the whole database, so everything written since the dump is lost. To bring back a single deleted garden, use the 7-day soft delete instead.

1. On your machine (operator credentials), make a short-lived download link. The instance role cannot read the bucket:

   ```sh
   aws s3 presign "s3://$BUCKET/db/fernslop-20261023T030000Z.dump" --expires-in 900
   ```

2. On the instance (SSM Session Manager, `sudo -i`):

   ```sh
   cd /opt/app
   URL='<the presigned URL>'
   docker compose stop app
   curl -fsS "$URL" | docker compose exec -T db \
     pg_restore -U fernslop -d fernslop --clean --if-exists --no-owner --single-transaction
   docker compose start app
   ```

   `--single-transaction` means a failed restore changes nothing. In that case, start `app` again and try another dump.

3. Check `/api/health` and that the gardens you expect are listed.

To restore into the local `make up` stack instead, start from step 2 in the repo root, using `< ./fernslop.dump` in place of `curl ... |`.
