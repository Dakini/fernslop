# Infra

`ec2-stack.yaml` runs Fernslop on one EC2 instance with docker compose (`db`, `app`, `caddy`) in `/opt/app`. `build.sh` builds one image per commit; `deploy.sh <env> <tag>` creates or updates the stack and deploys a tag.

## Build once, deploy a tag

`infra/build.sh` builds the arm64 image for `HEAD` and pushes it to ECR as `<repo>:<tag>`, where the tag is `YYYYMMDD-HHMMSS-<7-char sha>`: the commit's committer time in UTC plus its short sha, so the same commit always gives the same tag. There is no `:latest`. The tag is baked into the image (`--build-arg FERNSLOP_IMAGE_TAG`), so `/api/health` reports it as `version`.

```sh
infra/build.sh --print-tag   # print HEAD's tag; calls neither AWS nor docker
TAG=$(infra/build.sh)        # needs a clean tree and docker; skips the push if the tag is already in ECR
```

The last line on stdout is the tag, everything else goes to stderr. `APP_PREFIX` names the repository; `ECR_REPOSITORY_URI` (the repository URI) replaces the account lookup.

The ECR repository is immutable (a tag can never be pushed twice), expires untagged images after a day and keeps the last 50 tagged ones. A tag older than the last 50 builds is gone, so an environment that lags that far behind cannot pull its image again.

Each EC2 stack owns an SSM document, `<stack name>-deploy` (`fernslop-deploy`, `prod-fernslop-deploy`; stack output `DeployDocumentName`), with one parameter, `tag`, which must match the tag pattern. It logs in to ECR, replaces the `APP_TAG=` line in `/opt/app/.env` (leaving other lines alone), runs `docker compose up -d --pull always` and prunes images. The compose file's app image is `<repo>:${APP_TAG}`. If it is not, the document stops with a message instead of pulling something else. The stack's `ImageTag` parameter is only what a new or replaced instance boots; deploys never change it.

`deploy.sh <env> <tag>` refuses a missing tag, a bad format or a tag that is not in ECR before it changes anything. It builds nothing and does not deploy the ECR stack. On an existing stack it updates the EC2 stack (keeping its `ImageTag`), sends the stack's document, waits for it and then requires `/api/health` to report the tag. A first deploy creates the stack with `ImageTag=<tag>`.

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
TAG=$(infra/build.sh)
DOMAIN=fernslop.example.com infra/deploy.sh dev "$TAG"   # first deploy
infra/deploy.sh dev "$TAG"                                # later deploys
APP_PREFIX=myfork infra/deploy.sh prod --names
```

### One-time: move today's stacks onto the parameterised templates

Do this once, before the next `deploy.sh dev` or CI deploy (and before the next section), with operator credentials, from the repo root. It moves the live `fernslop` and `fernslop-ecr` stacks onto these templates with dev's names. You create each change set, check it, and only then execute it. Run step 4 at a quiet time: the instance stops and starts once, so expect about a minute of downtime.

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

   From then on, the stack's `AmiId` parameter holds the instance's AMI, so `deploy.sh dev` keeps it.

### One-time: build by tag and deploy through the SSM document

Do this once, after the section above, with operator credentials, from the repo root, on a clean checkout of the commit you want dev to run. Until you finish it, `deploy.sh dev <tag>` refuses the stack ("has no ImageTag yet"). Nothing here needs the instance to have the newer files (backup script, hardened compose file, Caddy config) that a freshly created stack gets: each step says what an older instance looks like.

1. **ECR change set.** The repository becomes immutable and gets the new lifecycle rule, and the stack gains the push role. The role trusts the GitHub OIDC provider that the `fernslop-github` stack owns, so find its ARN:

   ```sh
   OIDC=$(aws iam list-open-id-connect-providers --query "OpenIDConnectProviderList[?ends_with(Arn,'oidc-provider/token.actions.githubusercontent.com')].Arn" --output text)
   echo "$OIDC"   # one arn:aws:iam::<account>:oidc-provider/token.actions.githubusercontent.com
   aws cloudformation create-change-set --stack-name fernslop-ecr --change-set-name by-tag \
     --template-body file://infra/ecr-stack.yaml --capabilities CAPABILITY_IAM \
     --parameters ParameterKey=AppPrefix,ParameterValue=fernslop ParameterKey=ExistingOidcProviderArn,ParameterValue="$OIDC"
   aws cloudformation wait change-set-create-complete --stack-name fernslop-ecr --change-set-name by-tag
   aws cloudformation describe-change-set --stack-name fernslop-ecr --change-set-name by-tag --output table \
     --query "Changes[].ResourceChange.{Id:LogicalResourceId,Action:Action,Replacement:Replacement}"
   ```

   Expect `Repository` `Modify` with Replacement `False` and `EcrPushRole` `Add`; nothing `Remove`. If the OIDC provider is not listed, `fernslop-github` has not created it yet: stop. Execute, then check:

   ```sh
   aws cloudformation execute-change-set --stack-name fernslop-ecr --change-set-name by-tag
   aws cloudformation wait stack-update-complete --stack-name fernslop-ecr
   aws ecr describe-repositories --repository-names fernslop --query "repositories[0].imageTagMutability"   # IMMUTABLE
   aws ecr get-lifecycle-policy --repository-name fernslop --query lifecyclePolicyText --output text          # untagged 1 day, tagged 50
   aws cloudformation describe-stacks --stack-name fernslop-ecr --query "Stacks[0].Outputs" --output table  # EcrPushRoleArn, RepositoryUri
   ```

   Images already in the repository (including `:latest`, which the running instance uses) stay; `:latest` just cannot be pushed again. `EcrPushRoleArn` and `RepositoryUri` become the GitHub repository variables `ECR_PUSH_ROLE_ARN` and `ECR_REPOSITORY_URI` (next to `AWS_REGION`).

2. **Build the first tag.** Docker must be running.

   ```sh
   TAG=$(infra/build.sh)
   echo "$TAG"   # 20261023-190957-e7770e1 (yours differs)
   aws ecr describe-images --repository-name fernslop --image-ids imageTag="$TAG" --query "imageDetails[0].imageTags"
   ```

   The describe prints the tag. `build.sh` refuses a dirty tree and skips the push when the tag already exists, so it is safe to run again.

3. **EC2 change set (create it, do not execute yet).** It adds the `DeployDocument` and the `ImageTag` parameter and keeps every other parameter:

   ```sh
   aws cloudformation create-change-set --stack-name fernslop --change-set-name by-tag \
     --template-body file://infra/ec2-stack.yaml --capabilities CAPABILITY_IAM \
     --parameters ParameterKey=ImageTag,ParameterValue="$TAG" \
       ParameterKey=AppPrefix,UsePreviousValue=true ParameterKey=Environment,UsePreviousValue=true \
       ParameterKey=AmiId,UsePreviousValue=true ParameterKey=AllowPlainHttp,UsePreviousValue=true \
       ParameterKey=DomainName,UsePreviousValue=true ParameterKey=LatestAmiId,UsePreviousValue=true \
       ParameterKey=VpcId,UsePreviousValue=true ParameterKey=SubnetId,UsePreviousValue=true \
       ParameterKey=InstanceType,UsePreviousValue=true
   aws cloudformation wait change-set-create-complete --stack-name fernslop --change-set-name by-tag
   aws cloudformation describe-change-set --stack-name fernslop --change-set-name by-tag --output table \
     --query "Changes[].ResourceChange.{Id:LogicalResourceId,Action:Action,Replacement:Replacement,Scope:join(',',Scope)}"
   aws cloudformation describe-change-set --stack-name fernslop --change-set-name by-tag --output table \
     --query "Changes[?ResourceChange.LogicalResourceId=='Instance'].ResourceChange.Details[].Target.{Attribute:Attribute,Name:Name,Recreation:RequiresRecreation}"
   ```

   Check:

   - `DeployDocument` is `Add`. No row has Replacement `True` or `Conditional`, and nothing is `Remove`.
   - `Instance` is `Modify` and its details list only `UserData` (Recreation `Never`/`False`): the boot script now writes `APP_TAG` and the compose file uses it. UserData does not run again on an existing instance, so this changes nothing on it, but CloudFormation applies it with one stop and start, about a minute of downtime. Run step 4 at a quiet time.
   - If #234's section above was not completed on this stack, `Add` rows for resources newer than the live stack (`BackupBucket`, `BackupMissingAlarm`, ...) are expected, as they were there.

   If anything else shows up, delete the change set (`aws cloudformation delete-change-set --stack-name fernslop --change-set-name by-tag`) and report it.

4. **Execute it.**

   ```sh
   aws cloudformation execute-change-set --stack-name fernslop --change-set-name by-tag
   aws cloudformation wait stack-update-complete --stack-name fernslop
   aws cloudformation describe-stacks --stack-name fernslop --query "Stacks[0].Outputs[?OutputKey=='DeployDocumentName'].OutputValue" --output text   # fernslop-deploy
   aws ssm describe-document --name fernslop-deploy --query "Document.[Status,Parameters[0].Name]" --output text                                    # Active tag
   curl -fsS https://<DomainName>/api/health
   ```

   The app still runs the old `:latest` image, so health has no `version` yet.

5. **Point the live compose file at the tag.** The instance was built from an older template, so `/opt/app/docker-compose.yaml` still has the app image `...amazonaws.com/fernslop:latest`. Open an SSM session (`aws ssm start-session --target <InstanceId>`, then `sudo -i`) and edit it:

   ```sh
   cd /opt/app
   ls                                   # docker-compose.yaml must be there; stop and report if the file is named otherwise
   cp -p docker-compose.yaml docker-compose.yaml.bak
   sed -i 's#^\( *image: .*amazonaws\.com/[a-z0-9-]*\):latest *$#\1:${APP_TAG}#' docker-compose.yaml
   grep -n 'image:' docker-compose.yaml     # app: ...amazonaws.com/fernslop:${APP_TAG}; the other images unchanged
   grep -c ':latest' docker-compose.yaml    # 0
   ```

   The document needs nothing else from the older instance. It adds `APP_TAG` to `/opt/app/.env`: an older instance has a single `.env` with the database and app settings, and the document keeps every other line in it. A newer one has no `.env` and gets a new one (mode 600). If the `sed` matched nothing, edit the app image line by hand to end in `:${APP_TAG}`. Do not run `docker compose` here yourself; step 6 does.

6. **Deploy the tag.**

   ```sh
   infra/deploy.sh dev "$TAG"
   ```

   It checks the tag is in ECR, updates the stack with no changes (the same `ImageTag`), runs `fernslop-deploy` and waits. It ends with `Deployed <tag> to dev` once `curl https://<DomainName>/api/health` returns `"version":"<tag>"`. On a failure it prints the document's output; a "not deployed" message from the document means step 5 did not take. To see the document's last run: `aws ssm list-command-invocations --filters key=DocumentName,value=fernslop-deploy --details`.

   Later deploys are `TAG=$(infra/build.sh)` and `infra/deploy.sh dev "$TAG"`; CI does the same through the document ([#238](../backlog/238-env-ci-build-and-deploy-dev.md)).

## GitHub Actions deploy roles (one-time setup)

`github-oidc-stack.yaml` (stack `fernslop-github`) owns the account's GitHub OIDC provider (it is kept if the stack is deleted) and one deploy role per GitHub environment, so CI deploys without long-lived AWS keys:

| Role (stack output) | Trusts only | May send the document | To instances tagged `Name` |
| --- | --- | --- | --- |
| `DevelopmentDeployRole` (`DevelopmentDeployRoleArn`) | `Dakini/fernslop`, environment `development` | `<prefix>-deploy` (`fernslop-deploy`) | `<prefix>` (`fernslop`) |
| `ProductionDeployRole` (`ProductionDeployRoleArn`) | `Dakini/fernslop`, environment `production` | `prod-<prefix>-deploy` | `prod-<prefix>` |

A deploy role can do one thing: run its stack's SSM document ([build once, deploy a tag](#build-once-deploy-a-tag)) on its own instance, with a `tag` that matches the document's `allowedPattern` (an image that `build.sh` already pushed), and read the result (`ssm:GetCommandInvocation`, `ssm:ListCommandInvocations`). It cannot run `AWS-RunShellScript`, touch the other environment's document or instance, push or pull images, change a stack, or read the backups. CI never uses CloudFormation: stack changes stay manual, with operator credentials, as in the sections above.

The ECR push role is a separate role, in `ecr-stack.yaml` ([#235](../backlog/235-env-build-and-deploy-by-tag.md)). Only workflow runs on `main` can assume it, and it can only push to the repository. It trusts the provider that this stack owns, which is why the provider's ARN is a parameter of the ECR stack. The ECR stack's outputs `EcrPushRoleArn` and `RepositoryUri` become the repository variables `ECR_PUSH_ROLE_ARN` and `ECR_REPOSITORY_URI`, next to the repository-level `AWS_REGION`.

### One-time: replace the CloudFormation deploy role with the two environment roles

Do this once, with operator credentials, from the repo root. The live stack has the provider, `CloudFormationRole` and `DeployRole`. The new template removes the two roles and adds `DevelopmentDeployRole` and `ProductionDeployRole`.

1. **Create a change set** (do not execute it yet). The old `TrustSubject` parameter is gone, so pass the others:

   ```sh
   aws cloudformation create-change-set --stack-name fernslop-github --change-set-name env-roles \
     --template-body file://infra/github-oidc-stack.yaml --capabilities CAPABILITY_IAM \
     --parameters ParameterKey=AppPrefix,ParameterValue=fernslop \
       ParameterKey=GitHubRepo,UsePreviousValue=true ParameterKey=CreateOidcProvider,UsePreviousValue=true \
       ParameterKey=ExistingOidcProviderArn,UsePreviousValue=true
   aws cloudformation wait change-set-create-complete --stack-name fernslop-github --change-set-name env-roles
   aws cloudformation describe-change-set --stack-name fernslop-github --change-set-name env-roles \
     --query "Changes[].ResourceChange.[Action,LogicalResourceId,Replacement]" --output table
   ```

   Expect exactly: `GitHubOidcProvider` is not in the list at all (it is not `Remove` and not a replacement), `CloudFormationRole` and `DeployRole` are `Remove`, `DevelopmentDeployRole` and `ProductionDeployRole` are `Add`. If the provider shows up, or anything else is removed, do not execute: delete the change set (`aws cloudformation delete-change-set --stack-name fernslop-github --change-set-name env-roles`) and report what it showed. Use the same `AppPrefix` as the app stacks.

2. **Execute it.** The old CI deploy stops working from here, until [#238](../backlog/238-env-ci-build-and-deploy-dev.md) replaces it:

   ```sh
   aws cloudformation execute-change-set --stack-name fernslop-github --change-set-name env-roles
   aws cloudformation wait stack-update-complete --stack-name fernslop-github
   aws cloudformation describe-stacks --stack-name fernslop-github --query "Stacks[0].Outputs" --output table
   aws iam list-open-id-connect-providers   # the token.actions.githubusercontent.com provider is still listed
   ```

3. **Create the GitHub environments** `development` and `production` (repository Settings, Environments).

4. **Restrict `production` to `main`:** in the `production` environment, set Deployment branches and tags to "Selected branches and tags" and add `main`. The prod role trusts the environment, not the branch, so this setting is what keeps other branches out of prod.

5. **Set the variables** on each environment (Settings, Environments, Variables):

   | Variable | `development` | `production` |
   | --- | --- | --- |
   | `AWS_DEPLOY_ROLE_ARN` | stack output `DevelopmentDeployRoleArn` | stack output `ProductionDeployRoleArn` |
   | `AWS_REGION` | the region of the stacks, e.g. `eu-west-2` | the same |
   | `INSTANCE_ID` | `InstanceId` output of the `fernslop` stack | `InstanceId` output of the `prod-fernslop` stack |
   | `DEPLOY_DOCUMENT` | `DeployDocumentName` output of the `fernslop` stack (`fernslop-deploy`) | `DeployDocumentName` output of the `prod-fernslop` stack (`prod-fernslop-deploy`) |
   | `PUBLIC_URL` | `https://` plus the `fernslop` stack's `DomainName` | `https://` plus the `prod-fernslop` stack's `DomainName` |

   Production's values wait for [#237](../backlog/237-env-prod-stack-and-cutover.md), which creates the prod stack. Also set the repository variables `ECR_PUSH_ROLE_ARN`, `ECR_REPOSITORY_URI` and `AWS_REGION` from the `fernslop-ecr` stack's outputs. `INSTANCE_ID` changes when the instance is replaced: update the variable then.

   ```sh
   aws cloudformation describe-stacks --stack-name fernslop --query "Stacks[0].Outputs" --output table
   aws cloudformation describe-stacks --stack-name fernslop-ecr --query "Stacks[0].Outputs" --output table
   ```

To create the stack in an account that has none (not the live one): `aws cloudformation deploy --stack-name fernslop-github --template-file infra/github-oidc-stack.yaml --capabilities CAPABILITY_IAM`. If the account already has a `token.actions.githubusercontent.com` provider (an account can have only one; `aws iam list-open-id-connect-providers`), add `--parameter-overrides CreateOidcProvider=false ExistingOidcProviderArn=<arn>`.

Anyone who can push to `main` ships code to dev, and anyone who can run a `production` job ships a tag to prod. Protect `main` and the `production` environment accordingly.

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
