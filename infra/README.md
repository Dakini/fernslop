# Infra

`ec2-stack.yaml` runs Fernslop on one EC2 instance with docker compose (`db`, `app`, `caddy`) in `/opt/app`; `deploy.sh` creates or updates it.

## Environments and names

`deploy.sh <dev|prod>` deploys one environment. Run `infra/deploy.sh <env> --names` to print what it will use without calling AWS. Everything is named after an app prefix, `APP_PREFIX` (default `fernslop`; lowercase letters, digits and hyphens):

| | dev | prod |
| --- | --- | --- |
| EC2 stack, dashboard, instance tag `Name` | `<prefix>` | `prod-<prefix>` |
| Log group | `/<prefix>/app` | `/prod-<prefix>/app` |
| ECR stack and repository | `<prefix>-ecr`, `<prefix>` (shared) | `<prefix>-ecr`, `<prefix>` (shared) |

Dev keeps the names the single stack had before environments existed. Every resource that takes tags carries `App=<prefix>` and `Environment=<env>`; the shared ECR repository is tagged `Environment=shared`.

- `DOMAIN=<domain>` is read on the first deploy of an environment, and asked for if missing. On an existing stack, `deploy.sh` refuses a `DOMAIN` that differs from the stack's `DomainName`: changing the domain is a manual cutover, not a deploy.
- On every update, `deploy.sh` passes the running instance's AMI as `AmiId`. Without it, `LatestAmiId` would resolve to the newest Amazon Linux image and replace the instance, losing data since the last backup.

```sh
DOMAIN=fernslop.example.com infra/deploy.sh dev   # first deploy
infra/deploy.sh dev                                # later deploys
APP_PREFIX=myfork infra/deploy.sh prod --names
```

### One-time: move today's stacks onto the parameterised templates

Do this once, before the next `deploy.sh dev` or CI deploy, with operator credentials, from the repo root. It moves the live `fernslop` and `fernslop-ecr` stacks onto these templates with dev's names. You create each change set, check it, and only then execute it. Run step 4 at a quiet time: the instance stops and starts once, so expect about a minute of downtime.

1. **Backup script.** Add the `Environment` dimension to the instance's `/usr/local/bin/fernslop-backup`. The script is not replaced when the stack updates: `UserData` only runs on an instance's first boot. Then run one backup, so the alarm's new metric already has a data point:

   ```sh
   INSTANCE=$(aws cloudformation describe-stacks --stack-name fernslop \
     --query "Stacks[0].Outputs[?OutputKey=='InstanceId'].OutputValue" --output text)
   CMD=$(aws ssm send-command --instance-ids "$INSTANCE" --document-name AWS-RunShellScript \
     --parameters 'commands=["set -e","f=/usr/local/bin/fernslop-backup",
       "test -f $f || { echo \"no $f on this instance\"; exit 1; }",
       "grep -q -- \"--dimensions Environment=\" $f || sed -i \"s/--unit Count$/--unit Count --dimensions Environment=dev/\" $f",
       "grep -n -- --dimensions $f","systemctl start fernslop-backup"]' \
     --query Command.CommandId --output text)
   aws ssm wait command-executed --command-id "$CMD" --instance-id "$INSTANCE"
   aws ssm get-command-invocation --command-id "$CMD" --instance-id "$INSTANCE" \
     --query "[Status,StandardOutputContent,StandardErrorContent]" --output text
   ```

   Expect `Success` and the line ending `--dimensions Environment=dev`. If it says `no /usr/local/bin/fernslop-backup on this instance`, the instance was created before backups existed. Carry on, but `BackupMissingAlarm` will go to ALARM a day after step 4 until backups are installed on it.

2. **ECR change set.** Create it and list its changes:

   ```sh
   aws cloudformation create-change-set --stack-name fernslop-ecr --change-set-name env-params \
     --template-body file://infra/ecr-stack.yaml --parameters ParameterKey=AppPrefix,ParameterValue=fernslop
   aws cloudformation wait change-set-create-complete --stack-name fernslop-ecr --change-set-name env-params
   aws cloudformation describe-change-set --stack-name fernslop-ecr --change-set-name env-params --output table \
     --query "Changes[].ResourceChange.{Id:LogicalResourceId,Action:Action,Replacement:Replacement,Scope:join(',',Scope)}"
   ```

   Expect one row: `Repository`, `Modify`, Replacement `False`, Scope `Tags`.

3. **EC2 change set.** It pins the instance's current AMI and keeps every other parameter:

   ```sh
   AMI=$(aws ec2 describe-instances --instance-ids "$INSTANCE" \
     --query "Reservations[0].Instances[0].ImageId" --output text)
   aws cloudformation create-change-set --stack-name fernslop --change-set-name env-params \
     --template-body file://infra/ec2-stack.yaml --capabilities CAPABILITY_IAM \
     --parameters ParameterKey=AppPrefix,ParameterValue=fernslop ParameterKey=Environment,ParameterValue=dev \
       ParameterKey=AmiId,ParameterValue="$AMI" ParameterKey=AllowPlainHttp,ParameterValue=false \
       ParameterKey=DomainName,UsePreviousValue=true ParameterKey=LatestAmiId,UsePreviousValue=true \
       ParameterKey=VpcId,UsePreviousValue=true ParameterKey=SubnetId,UsePreviousValue=true \
       ParameterKey=InstanceType,UsePreviousValue=true
   aws cloudformation wait change-set-create-complete --stack-name fernslop --change-set-name env-params
   aws cloudformation describe-change-set --stack-name fernslop --change-set-name env-params --output table \
     --query "Changes[].ResourceChange.{Id:LogicalResourceId,Action:Action,Replacement:Replacement,Scope:join(',',Scope)}"
   # What changes on the instance itself
   aws cloudformation describe-change-set --stack-name fernslop --change-set-name env-params --output table \
     --query "Changes[?ResourceChange.LogicalResourceId=='Instance'].ResourceChange.Details[].Target.{Attribute:Attribute,Name:Name,Recreation:RequiresRecreation}"
   ```

   Check:

   - No row has Replacement `True` or `Conditional`.
   - `Instance` is `Modify`. Its details list only `UserData` (Properties) and the tags (Tags), none with Recreation `Always` or `Conditionally`. A `UserData` change means one short stop/start; there must be no `ImageId` row.
   - The other rows are `Modify` with Replacement `False`: tags on `LogGroup`, `SecurityGroup`, `InstanceRole`, `ElasticIp` and `RecoveryAlarm`, and the backup metric's dimension on `Dashboard`.
   - Rows that are `Add` are resources added to the template since the stack was last deployed (for example `BackupBucket`, `BackupBucketPolicy` and `BackupMissingAlarm`, with the backup policy on `InstanceRole`). Nothing may be `Remove`.

   If anything else shows up, do not execute. Delete the change set (`aws cloudformation delete-change-set --stack-name fernslop --change-set-name env-params`) and report what it showed.

4. **Execute, at a quiet time.** The ECR change first, then the EC2 one. Expect about a minute of downtime while the instance stops and starts:

   ```sh
   aws cloudformation execute-change-set --stack-name fernslop-ecr --change-set-name env-params
   aws cloudformation wait stack-update-complete --stack-name fernslop-ecr
   aws cloudformation execute-change-set --stack-name fernslop --change-set-name env-params
   aws cloudformation wait stack-update-complete --stack-name fernslop
   curl -fsS https://<DomainName>/api/health
   ```

   From then on, the stack's `AmiId` parameter holds the instance's AMI, so `deploy.sh dev` (and CI, which cannot read EC2 instances) keeps it.

## GitHub Actions deploy role (one-time setup)

`github-oidc-stack.yaml` (stack `fernslop-github`) lets GitHub Actions run `deploy.sh` without long-lived AWS keys. It creates two roles:

- **Deploy role:** assumed through GitHub OIDC. Only `Dakini/fernslop` can assume it, and only from `main` or from the `production` environment, depending on the setting below. It can run change sets on `fernslop` and `fernslop-ecr`, push to the `fernslop` ECR repository and run `AWS-RunShellScript` on the instance tagged `Name=fernslop`. It has no IAM write and no S3 access, so it cannot read the backups.
- **CloudFormation role:** the role that stack updates run as.

Deploy the stack yourself with operator credentials. `deploy.sh` never touches it. Pick one of these commands:

```sh
# Trust pushes to main (default), creating the account's GitHub OIDC provider
aws cloudformation deploy --stack-name fernslop-github --template-file infra/github-oidc-stack.yaml \
  --capabilities CAPABILITY_IAM

# Trust only jobs that use the GitHub "production" environment
aws cloudformation deploy --stack-name fernslop-github --template-file infra/github-oidc-stack.yaml \
  --capabilities CAPABILITY_IAM --parameter-overrides TrustSubject=production-environment

# The account already has the provider (add TrustSubject=... as above if wanted)
aws cloudformation deploy --stack-name fernslop-github --template-file infra/github-oidc-stack.yaml \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides CreateOidcProvider=false ExistingOidcProviderArn=<arn>
```

An account can have only one provider for `token.actions.githubusercontent.com`. To check whether it already exists and get its ARN, run `aws iam list-open-id-connect-providers`.

`production-environment` only works once the `production` environment exists in the GitHub repository settings and the deploy job names it (`environment: production`). Until then, no job can assume the role.

Then set these GitHub repository variables, which the deploy workflow reads:

| Variable | Value |
| --- | --- |
| `AWS_DEPLOY_ROLE_ARN` | stack output `DeployRoleArn` |
| `AWS_CFN_ROLE_ARN` | stack output `CloudFormationRoleArn`. The workflow passes it to `deploy.sh` as `CFN_ROLE_ARN`, which then adds `--role-arn` to its `cloudformation deploy` calls. Without it, `deploy.sh` runs exactly as before. |
| `AWS_REGION` | the region of the stacks, e.g. `eu-west-2` |

```sh
aws cloudformation describe-stacks --stack-name fernslop-github --query "Stacks[0].Outputs" --output table
```

Anyone who can push to `main`, or approve a `production` deployment, can change `ec2-stack.yaml`. That includes the instance role's policies. Protect that branch or environment accordingly.

## Database backups

Every night at 03:00 UTC (or at the next boot if the instance was off then) the `fernslop-backup.timer` systemd timer runs `/usr/local/bin/fernslop-backup`. That script streams `pg_dump -Fc` from the compose `db` straight to S3; the dump never lands on the instance's disk. It then records a `Fernslop/BackupSucceeded` metric with an `Environment` dimension (`dev` or `prod`).

- **Where:** `s3://<BackupBucketName>/db/fernslop-<UTC timestamp>.dump`, where `BackupBucketName` is a stack output. Objects are encrypted (SSE-S3), the bucket blocks all public access and refuses non-TLS requests, and dumps expire after 30 days. The bucket is kept when the stack is deleted.
- **Who can read them:** only operator credentials. The instance role can only write under `db/`, so it cannot list, read or delete earlier dumps.
- **Alarm:** `BackupMissingAlarm` goes to ALARM after 26 hours without a `BackupSucceeded` data point for its own environment, so one environment's backups cannot hide another's missing ones. The environment's dashboard (`fernslop` for dev) shows it next to a per-day count of backups. To see why a run failed, use `journalctl -u fernslop-backup` on the instance.
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
