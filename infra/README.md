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

## CI: build and deploy to dev

`.github/workflows/ci.yaml` runs the tests on every push and pull request. On a push to `main`, once `backend`, `frontend` and `stack` pass, two more jobs run:

1. **`build-and-push`** assumes the ECR push role (`ECR_PUSH_ROLE_ARN`) and runs `infra/build.sh` once. It builds for arm64 (QEMU and buildx) and pushes `<repo>:<tag>`, skipping the push if the tag is already in ECR. The tag is its job output. Nothing else builds or pushes.
2. **`deploy-dev`** (GitHub environment `development`) assumes the dev deploy role and sends the stack's SSM document (`DEPLOY_DOCUMENT`) to the instance (`INSTANCE_ID`) with that tag, then waits for it. Then it polls `PUBLIC_URL/api/health` for about 2 minutes until it returns 200 with `version` equal to the tag, and runs a read-only smoke test: `GET /` returns HTML and `GET /api/plants` returns a non-empty JSON array. Only after all of that does it move the git tag `deployed-dev` to the commit (`git tag -f` and a forced push, with the job's own token; this is the only job with `contents: write`). A failed deploy, health check or smoke test leaves the tag where it was. Nothing is rolled back.

No CI job calls CloudFormation or `deploy.sh`; creating or changing a stack stays with the operator. A newer push can replace a queued `main` run, so not every commit reaches dev.

Variables (GitHub repository settings, Variables):

| Where | Variable | Value |
| --- | --- | --- |
| repository | `ECR_PUSH_ROLE_ARN` | `fernslop-ecr` output `EcrPushRoleArn` |
| repository | `AWS_REGION` | the region of the stacks, e.g. `eu-west-2` |
| repository, optional | `ECR_REPOSITORY_URI` | `fernslop-ecr` output `RepositoryUri`; without it `build.sh` derives the repository from the account |
| `development` environment | `AWS_DEPLOY_ROLE_ARN` | the development deploy role of the `fernslop-github` stack ([#236](../backlog/236-env-iam-split-per-environment.md)) |
| `development` environment | `INSTANCE_ID` | the dev instance, e.g. `i-0123456789abcdef0` (stack output `InstanceId`) |
| `development` environment | `DEPLOY_DOCUMENT` | `fernslop-deploy` (stack output `DeployDocumentName`) |
| `development` environment | `PUBLIC_URL` | `https://<DomainName>`, no path (stack output `Url`) |

`deploy-dev` stops with one line, before any AWS call, if any of `AWS_DEPLOY_ROLE_ARN`, `AWS_REGION`, `INSTANCE_ID`, `DEPLOY_DOCUMENT` or `PUBLIC_URL` is empty. `AWS_REGION` is read from the repository unless the `development` environment sets its own.

**Rerunning only a failed `deploy-dev`** ("Re-run failed jobs") reuses the tag that `build-and-push` produced in that run: it does not build again, and it deploys that run's commit even if `main` has moved on. To deploy a newer commit, push it. If `build-and-push` itself failed, rerunning it is safe, because `build.sh` skips a tag that is already in ECR.

Actions are pinned to a full commit SHA with the release tag in a comment (`aws-actions/configure-aws-credentials` is `v6.3.0`, shared with the prod workflow). Check a change to the workflow with `actionlint`, for example `uvx --with shellcheck-py --from actionlint-py actionlint`.

## Promote to prod

`.github/workflows/promote.yaml` deploys to prod the exact image that dev runs. It builds nothing. Start it by hand from the Actions tab ("Promote to prod", Run workflow, branch `main`) or with `gh workflow run promote.yaml --ref main`. It has no inputs and no approval step.

It fails at once unless it runs from `main`, then checks out the git tag `deployed-dev` (the commit CI's `deploy-dev` last proved live on dev; the run stops with a message if the tag does not exist yet) and takes the image tag from `infra/build.sh --print-tag` on that commit. As `deploy-dev` does, it sends the SSM document to the prod instance with that tag, waits for it, and then polls `PUBLIC_URL/api/health` for about 2 minutes until it returns 200 with `status` `ok` and `version` equal to the tag. The tag and the result go to the run summary. Nothing is rolled back: a red run leaves prod as the SSM document left it.

Variables of the GitHub environment `production` (Settings, Environments):

| Variable | Value |
| --- | --- |
| `AWS_DEPLOY_ROLE_ARN` | the production deploy role of the `fernslop-github` stack ([#236](../backlog/236-env-iam-split-per-environment.md)) |
| `INSTANCE_ID` | the prod instance (stack output `InstanceId`) |
| `DEPLOY_DOCUMENT` | the prod stack's document, `prod-fernslop-deploy` (stack output `DeployDocumentName`) |
| `PUBLIC_URL` | `https://<DomainName>`, no path (stack output `Url`) |
| `AWS_REGION` | the repository's value is used unless the environment sets its own |

The run stops before any AWS call if any of these five is empty.

**Limit the `production` environment's deployment branches to `main`** (Settings, Environments, production, Deployment branches and tags). The prod role trusts the environment, not the branch, so without this a workflow run from another branch could use the role. The workflow's own `main` check is a second guard, not a replacement.

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

   Production's values wait for the prod stack, which [the cutover](#one-time-cut-over-to-prod) creates ([#237](../backlog/237-env-prod-stack-and-cutover.md)) and sets them after. Also set the repository variables `ECR_PUSH_ROLE_ARN`, `ECR_REPOSITORY_URI` and `AWS_REGION` from the `fernslop-ecr` stack's outputs. `INSTANCE_ID` changes when the instance is replaced: update the variable then.

   ```sh
   aws cloudformation describe-stacks --stack-name fernslop --query "Stacks[0].Outputs" --output table
   aws cloudformation describe-stacks --stack-name fernslop-ecr --query "Stacks[0].Outputs" --output table
   ```

To create the stack in an account that has none (not the live one): `aws cloudformation deploy --stack-name fernslop-github --template-file infra/github-oidc-stack.yaml --capabilities CAPABILITY_IAM`. If the account already has a `token.actions.githubusercontent.com` provider (an account can have only one; `aws iam list-open-id-connect-providers`), add `--parameter-overrides CreateOidcProvider=false ExistingOidcProviderArn=<arn>`.

Anyone who can push to `main` ships code to dev, and anyone who can run a `production` job ships a tag to prod. Protect `main` and the `production` environment accordingly.

## One-time: cut over to prod

Do this once, with operator credentials, from the repo root, to turn today's instance into dev and put the live site on a new prod stack. At the end, `https://fernslop.example.com` is prod and holds the live data, and `https://dev-fernslop.example.com` is the old instance, with a copy of that data. Each step has a **Check** and an **Undo**. Steps 1 and 2 can be done days ahead and change nothing live. Steps 3 to 7 are one sitting: dev answers errors from the freeze (step 3) until the DNS switch (step 7), about 20 to 30 minutes. Step 9 stops and starts dev once more, for about a minute.

Names: the dev stack is `fernslop`, the prod stack `prod-fernslop` ([environments and names](#environments-and-names)). The live domain is `fernslop.example.com`, the dev one `dev-fernslop.example.com`. Dev's domain stays one level deep, so Cloudflare's certificate covers it. Both A records are DNS only (grey cloud): the certificates come from Caddy on each instance.

**Start here.** These must be done already (follow their sections, do not repeat them here): [move today's stacks onto the parameterised templates](#one-time-move-todays-stacks-onto-the-parameterised-templates) ([#234](../backlog/done/234-env-parameterise-stacks.md)), [build by tag and deploy through the SSM document](#one-time-build-by-tag-and-deploy-through-the-ssm-document) ([#235](../backlog/done/235-env-build-and-deploy-by-tag.md)) and [replace the CloudFormation deploy role with the two environment roles](#one-time-replace-the-cloudformation-deploy-role-with-the-two-environment-roles) ([#236](../backlog/done/236-env-iam-split-per-environment.md)). Use a clean checkout of `main`, the same one for the whole cutover, so the stack templates do not change under you. Then:

```sh
TAG=$(curl -fsS https://fernslop.example.com/api/health | sed -n 's/.*"version" *: *"\([^"]*\)".*/\1/p')
echo "$TAG"   # 20261023-190957-e7770e1 (yours differs): the tag dev runs now, built by infra/build.sh
aws ecr describe-images --repository-name fernslop --image-ids imageTag="$TAG" --query "imageDetails[0].imageTags"
aws cloudformation describe-stacks --stack-name fernslop-github --query "Stacks[0].Outputs[].OutputKey" --output text   # includes ProductionDeployRoleArn
aws cloudformation describe-stacks --stack-name prod-fernslop   # must fail: "does not exist"
out() { aws cloudformation describe-stacks --stack-name "$1" --query "Stacks[0].Outputs[?OutputKey=='$2'].OutputValue" --output text; }
DEV_INSTANCE=$(out fernslop InstanceId); DEV_IP=$(out fernslop ElasticIp)
```

If `TAG` is empty, dev does not run a tagged image yet: finish #235's section first. Prod must run the same tag as the dump's source, because the dump has dev's schema. Keep `TAG`, `out`, `DEV_INSTANCE` and `DEV_IP` in your shell, or set them again.

On an instance (SSM Session Manager: `aws ssm start-session --target <InstanceId>`, then `sudo -i` and `cd /opt/app`), the steps below use this helper to call the app from inside its container, since the app's port is not published and prod has no certificate yet. Paste it into each session:

```sh
get() { docker compose exec -T app python -c 'import sys, urllib.request as u; r = u.urlopen("http://localhost:8000" + sys.argv[1]); b = r.read(); t = r.headers.get("content-type", ""); print(r.status, t, len(b), b[:200].decode() if "json" in t else "")' "$1"; }
get /api/health   # 200 application/json <bytes> {"status":"ok","version":"<tag>"}
```

**Rule for the whole cutover:** dev's `app` stays stopped from step 3 until a step below starts it, and nothing else may start it. Do not push to `main`, do not run "Promote to prod", do not run `infra/deploy.sh dev` and do not run `docker compose up -d` on dev meanwhile. A CI deploy runs `docker compose up -d` through the SSM document and would start `app` again, serving stale data under the live domain. The freeze ends after step 9.

1. **Create prod.** Check the names, then create the stack with the tag dev runs:

   ```sh
   infra/deploy.sh prod --names     # stack prod-fernslop, deploy doc prod-fernslop-deploy; calls no AWS
   DOMAIN=fernslop.example.com infra/deploy.sh prod "$TAG"
   ```

   The stack is created with `ImageTag=$TAG`. The script then waits for `https://fernslop.example.com/api/health` to report the tag, and that wait **will fail**: Caddy gets its certificate only once DNS points at prod (step 7), so after about 10 minutes it prints `Not reporting ... after 10 minutes` and exits 1. That is expected; you can stop it with Ctrl-C once it prints `Waiting for`. It also prints a line asking you to create a DNS A record: do not, until step 7. Until then every certificate attempt by prod's Caddy fails, and Let's Encrypt limits failed attempts per hour, so the check below stops prod's Caddy.

   Check: the stack exists, and the app is healthy on the instance (the first boot takes a few minutes after the stack says `CREATE_COMPLETE`, because CloudFormation does not wait for the boot script):

   ```sh
   aws cloudformation describe-stacks --stack-name prod-fernslop --query "Stacks[0].StackStatus" --output text   # CREATE_COMPLETE
   PROD_INSTANCE=$(out prod-fernslop InstanceId); PROD_IP=$(out prod-fernslop ElasticIp); BUCKET=$(out prod-fernslop BackupBucketName)
   echo "$PROD_INSTANCE $PROD_IP $BUCKET"
   aws ssm start-session --target "$PROD_INSTANCE"   # then: sudo -i; cd /opt/app; paste get() from above
   ```

   On the instance:

   ```sh
   tail -n 1 /var/log/cloud-init-output.log   # === bootstrap complete ===
   docker compose ps                          # db healthy, app and caddy running
   get /api/health                            # 200 application/json ... {"status":"ok","version":"<TAG>"}
   docker compose stop caddy                  # no certificate attempts until step 7
   ```

   If `get` fails, `docker compose logs app` and `docker compose logs db` say why; the CloudWatch log group `/prod-fernslop/app` has the same. If the session will not start, the instance is still booting: wait a minute.

   Undo: `aws cloudformation delete-stack --stack-name prod-fernslop`, then `aws cloudformation wait stack-delete-complete --stack-name prod-fernslop`. The backup bucket is kept when a stack is deleted: empty and delete it by hand (`aws s3 rb "s3://$BUCKET" --force`) if you will not create prod again. Nothing live has changed.

2. **Set prod's GitHub values.** Set the `production` environment's variables as in [step 5 of the environment roles section](#one-time-replace-the-cloudformation-deploy-role-with-the-two-environment-roles): `AWS_DEPLOY_ROLE_ARN` is the `fernslop-github` output `ProductionDeployRoleArn`, `INSTANCE_ID` is `$PROD_INSTANCE`, `DEPLOY_DOCUMENT` is `prod-fernslop-deploy`, `PUBLIC_URL` is `https://fernslop.example.com`, and `AWS_REGION` comes from the repository unless you set one. The environment itself and its `main`-only branch rule come from that section's steps 3 and 4.

   Check: the values show in Settings, Environments, production, and `aws cloudformation describe-stacks --stack-name prod-fernslop --query "Stacks[0].Outputs[?OutputKey=='DeployDocumentName'].OutputValue" --output text` prints `prod-fernslop-deploy`. Do not run "Promote to prod" yet.

   Undo: clear the variables. A promote run stops before any AWS call while one is empty.

3. **Freeze dev and dump it.** Announce it first, because nobody may push to `main` or promote until step 9. Check Actions shows no run in progress. In an SSM session on dev (`aws ssm start-session --target "$DEV_INSTANCE"`, `sudo -i`, `cd /opt/app`, paste `get()`), stop the app and the housekeeping timers (they run one-off app containers that would change rows after the dump; an older instance may not have them), then dump:

   ```sh
   systemctl stop fernslop-photo-cleanup.timer fernslop-room-purge.timer || true
   docker compose stop app
   docker compose ps                                  # db healthy and caddy running; app is not
   df -h /                                            # room for the dump on the 20 GB disk
   umask 077
   docker compose exec -T db pg_dump -U fernslop -d fernslop -Fc > /root/cutover.dump && echo dumped
   ls -l /root/cutover.dump                           # -rw------- 1 root root <size>, size above 0
   docker compose exec -T db pg_restore --list < /root/cutover.dump >/dev/null && echo "dump is readable"
   stat -c %s /root/cutover.dump                      # note this size for step 4
   ```

   The dump is custom format and stays on dev's disk, readable by root only (`umask 077` and `/root`). If `pg_dump` fails with a role or database that does not exist, `docker compose exec db env | grep POSTGRES_` shows the real names of this older instance; use them here, in the restore, and in `infra/table-counts.sh`, which assumes `fernslop`. Dev has no `fernslop-backup`, backup bucket or alarm ([#234's engineer comment](../backlog/done/234-env-parameterise-stacks.md)), so none of that is used here; the dump goes to prod's bucket in step 4.

   Then, on your machine, count the rows per table. The helper runs one `SELECT` on the instance and prints `<table> <count>` lines (no row contents):

   ```sh
   infra/table-counts.sh dev | tee "${TMPDIR:-/tmp}/dev-counts.txt"
   ```

   Check: the dump is listed as readable, its size is not 0, and the counts list `rooms`, `feed_events`, `photos` and the other tables.

   Undo, which loses nothing: `rm -f /root/cutover.dump`, `docker compose start app`, `systemctl start fernslop-photo-cleanup.timer fernslop-room-purge.timer || true`, then `get /api/health` and tell the team the freeze is over.

4. **Upload the dump to prod's bucket.** This needs no new infrastructure: prod's own backup bucket takes it under `db/`, which the nightly job also uses. `aws s3 presign` only makes download links, so make the 15-minute upload link with `uvx` (a one-off `boto3`, not a project dependency). It signs against the regional S3 endpoint, because the global one answers a new bucket with a redirect that `curl -T` does not follow:

   ```sh
   KEY="db/cutover-$(date -u +%Y%m%dT%H%M%SZ).dump"
   PUT_URL=$(uvx --from boto3 python -I - "$BUCKET" "$KEY" <<'PY'
   import sys

   import boto3
   from botocore.config import Config

   bucket, key = sys.argv[1:3]
   session = boto3.Session()
   region = session.region_name or sys.exit("No region: set AWS_DEFAULT_REGION or run aws configure")
   s3 = session.client("s3", endpoint_url=f"https://s3.{region}.amazonaws.com", config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}))
   print(s3.generate_presigned_url("put_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=900))
   PY
   )
   echo "$KEY"; echo "$PUT_URL"   # https://<bucket>.s3.<region>.amazonaws.com/db/cutover-...dump?X-Amz-...&X-Amz-Expires=900&...
   ```

   Paste the URL into dev's session and upload. The URL lets whoever holds it write that one key for 15 minutes:

   ```sh
   URL='<the PUT URL>'
   curl -fsS -T /root/cutover.dump "$URL" && echo uploaded
   ```

   Check: on your machine, `aws s3 ls "s3://$BUCKET/$KEY"` shows the same size in bytes as `stat -c %s` on dev. If the link has expired (a `403`), run the first block again for a new link.

   Undo: `aws s3 rm "s3://$BUCKET/$KEY"`. The link stops working by itself after 15 minutes.

5. **Restore into prod.** Make a download link on your machine, as in [step 1 of the restore steps](#restore-into-the-instances-compose-db), but for the cutover object:

   ```sh
   aws s3 presign "s3://$BUCKET/$KEY" --expires-in 900
   ```

   In a session on prod (`sudo -i`, `cd /opt/app`, paste `get()`), stop the housekeeping timers until step 6 is done, so no row changes between the restore and the count:

   ```sh
   systemctl stop fernslop-photo-cleanup.timer fernslop-room-purge.timer
   ```

   Then follow [steps 2 and 3 of the restore steps](#restore-into-the-instances-compose-db): stop `app`, pipe the download into `pg_restore --single-transaction`, start `app`, check `/api/health`. They are linked, not copied here. Prod's Caddy is still stopped, which is right.

   Check: `pg_restore` printed no error, and `get /api/health` answers `200` with the tag. A failed restore changed nothing (`--single-transaction`): start `app`, check the link has not expired, and run it again.

   Undo: the restore replaces prod's database, which holds nothing live yet, so run it again with another dump, or rebuild prod with step 1's undo.

6. **Verify the data.** On your machine, the counts on prod must equal dev's from step 3:

   ```sh
   infra/table-counts.sh prod > "${TMPDIR:-/tmp}/prod-counts.txt"
   diff "${TMPDIR:-/tmp}/dev-counts.txt" "${TMPDIR:-/tmp}/prod-counts.txt" && echo "row counts match"
   ```

   Then open a garden that has a photo, on prod's instance, with the `get` helper (the live site has no certificate until step 7):

   ```sh
   docker compose exec -T db psql -U fernslop -d fernslop -Atc "select room_id, photo_url from feed_events where photo_url is not null order by seq desc limit 3"
   get /api/rooms/<room_id>        # 200 application/json (a 404 is a deleted garden: use the next row)
   get /api/photos/<photo id>      # 200 image/jpeg (or png, webp): the photo_url path from the same row
   systemctl start fernslop-photo-cleanup.timer fernslop-room-purge.timer
   ```

   Check: `diff` prints nothing and says `row counts match`, and both `get` calls answer 200. You will open the same garden in a browser after step 7. Do not go on if the counts differ: a difference in `photos` alone usually means a housekeeping timer ran on one side, so count both again.

   Undo: nothing to undo; it only reads. If a check fails, stay here: the live site is still dev, and dev's `app` is still stopped (the site answers errors). To give up, undo step 4 (delete the object) and step 3 (start dev's `app` again); nothing is lost.

7. **Switch the DNS.** This is the cutover: from here on, writes go to prod. In Cloudflare (DNS, Records), edit the `fernslop` A record from dev's Elastic IP to prod's, proxy status DNS only. Write down the old value first (`echo "$DEV_IP"` has it). Then wait until it resolves, and start prod's Caddy, which gets its certificate once the name resolves to it:

   ```sh
   echo "$PROD_IP"
   dig +short fernslop.example.com @1.1.1.1    # prints $PROD_IP
   ```

   On prod's instance:

   ```sh
   docker compose start caddy
   docker compose logs --since 5m caddy | grep -iE 'certificate obtained|error'
   ```

   Check, from your machine:

   ```sh
   curl -fsS https://fernslop.example.com/api/health   # {"status":"ok","version":"<TAG>"}
   ```

   Then open `https://fernslop.example.com` in a browser and open the garden with a photo from step 6. If there is no certificate after about 5 minutes, the Caddy log says why. Run `docker compose restart caddy` on prod to try again at once, once `dig` shows `$PROD_IP`.

   Undo (the rollback), in this order. If step 9 is already done, undo its parts first, 9e to 9b, so that dev's `app` is stopped again. Set the A record back to `$DEV_IP` and wait until `dig +short fernslop.example.com @1.1.1.1` shows it. Only then start dev: on dev run `docker compose start app` and `systemctl start fernslop-photo-cleanup.timer fernslop-room-purge.timer || true`. On prod run `docker compose stop app caddy`. If nobody has used prod yet, nothing is lost. If prod has taken writes, everything written to prod since this step is lost: dump it first on prod with `docker compose exec -T db pg_dump -U fernslop -d fernslop -Fc > /root/prod.dump` if it matters, and delete that file afterwards.

8. **Back up prod once.** On prod's instance run `systemctl start fernslop-backup`. Then, on your machine, check the object and that it is readable, as in [download a dump](#download-a-dump-operator-credentials) but with prod's `$BUCKET` from step 1:

   ```sh
   aws s3 ls "s3://$BUCKET/db/"      # a fernslop-<UTC timestamp>.dump next to cutover-....dump
   aws s3 cp "s3://$BUCKET/db/fernslop-<UTC timestamp>.dump" ./prod-check.dump
   pg_restore --list ./prod-check.dump >/dev/null && echo "dump is readable"   # or in a postgres:17-alpine container
   rm -f ./prod-check.dump
   ```

   Check: the object is listed and `dump is readable` prints. `journalctl -u fernslop-backup` on the instance says why if not. Also `systemctl list-timers fernslop-backup.timer` on the instance shows the next 03:00 UTC run.

   Undo: nothing to undo; delete the object with `aws s3 rm` if you want.

9. **Move dev to its own name.** Dev keeps running, now on `dev-fernslop.example.com`. Five parts, in this order.

   **9a. DNS.** In Cloudflare add an A record `dev-fernslop` to `$DEV_IP`, DNS only. Check: `dig +short dev-fernslop.example.com @1.1.1.1` prints `$DEV_IP`. Undo: delete the record.

   **9b. The files on dev.** In a session on dev, find where the older instance keeps the live name. A newer one has `SITE_ADDRESS` in `caddy.env` and `FERNSLOP_PUBLIC_URL` in `app.env`; an older one may have both in `.env`, or the name in the `Caddyfile` or the compose file:

   ```sh
   cd /opt/app
   grep -rnIE --exclude='*.bak' '(^|[^-.a-z0-9])fernslop\.example\.com' .   # every file that holds the live name
   ```

   Edit exactly the files it lists, keeping a copy of each. For the newer layout (the same two `sed` lines work on a single `.env`; in a `Caddyfile` or compose file, change the name by hand):

   ```sh
   cp -p caddy.env caddy.env.bak; cp -p app.env app.env.bak
   sed -i 's#^SITE_ADDRESS=.*#SITE_ADDRESS=dev-fernslop.example.com#' caddy.env
   sed -i 's#^FERNSLOP_PUBLIC_URL=.*#FERNSLOP_PUBLIC_URL=https://dev-fernslop.example.com#' app.env
   grep -rnIE --exclude='*.bak' '(^|[^-.a-z0-9])fernslop\.example\.com' .   # prints nothing
   grep -rnI --exclude='*.bak' 'dev-fernslop' .                                 # the two new lines
   ```

   Check: the first `grep` prints nothing and the second shows the new lines. Undo: `mv caddy.env.bak caddy.env; mv app.env.bak app.env`.

   **9c. Restart Caddy and start the app.** Dev's `app` is still stopped, and it starts only now that the files name the dev domain. Recreate both containers so they read the new values (`docker compose restart` does not re-read an env file), and start the housekeeping timers again:

   ```sh
   docker compose up -d --force-recreate --no-deps caddy app
   systemctl start fernslop-photo-cleanup.timer fernslop-room-purge.timer || true
   docker compose ps                                              # db, app and caddy running
   docker compose logs --since 3m caddy | grep -iE 'certificate obtained|error'
   get /api/health
   ```

   Check, from your machine: `curl -fsS https://dev-fernslop.example.com/api/health` prints the tag. Undo: `docker compose stop app`, put the `.bak` files back as in 9b, and `docker compose up -d --force-recreate --no-deps caddy`.

   **9d. The stack's `DomainName`.** Set it to match, so the stack's `Url` output and `deploy.sh`'s health wait use the new name. Create a change set and review it before you execute it. The change touches the instance's user data, which runs only on first boot, so the edits above are what moved dev; CloudFormation applies the change with one stop and start of the instance, about a minute, which is acceptable because dev serves no users after the cutover:

   ```sh
   aws cloudformation create-change-set --stack-name fernslop --change-set-name dev-domain \
     --template-body file://infra/ec2-stack.yaml --capabilities CAPABILITY_IAM \
     --parameters ParameterKey=DomainName,ParameterValue=dev-fernslop.example.com \
       ParameterKey=AppPrefix,UsePreviousValue=true ParameterKey=Environment,UsePreviousValue=true \
       ParameterKey=ImageTag,UsePreviousValue=true ParameterKey=AmiId,UsePreviousValue=true \
       ParameterKey=AllowPlainHttp,UsePreviousValue=true ParameterKey=LatestAmiId,UsePreviousValue=true \
       ParameterKey=VpcId,UsePreviousValue=true ParameterKey=SubnetId,UsePreviousValue=true \
       ParameterKey=InstanceType,UsePreviousValue=true
   aws cloudformation wait change-set-create-complete --stack-name fernslop --change-set-name dev-domain
   aws cloudformation describe-change-set --stack-name fernslop --change-set-name dev-domain --output table \
     --query "Changes[].ResourceChange.{Id:LogicalResourceId,Action:Action,Replacement:Replacement,Scope:join(',',Scope)}"
   aws cloudformation describe-change-set --stack-name fernslop --change-set-name dev-domain --output table \
     --query "Changes[?ResourceChange.LogicalResourceId=='Instance'].ResourceChange.Details[].Target.{Attribute:Attribute,Name:Name,Recreation:RequiresRecreation}"
   ```

   Expect one row: `Instance`, `Modify`, Replacement `False`, with details listing only `UserData`. **Stop on `Replacement: True`**, and on `Conditional`, any `Remove`, or any other row: a replaced instance loses dev's data. Delete the change set (`aws cloudformation delete-change-set --stack-name fernslop --change-set-name dev-domain`) and report what it showed; dev already runs on the new name by hand, and only the stack's parameter lags. If it is clean, execute it:

   ```sh
   aws cloudformation execute-change-set --stack-name fernslop --change-set-name dev-domain
   aws cloudformation wait stack-update-complete --stack-name fernslop
   out fernslop Url                                          # https://dev-fernslop.example.com
   curl -fsS https://dev-fernslop.example.com/api/health
   ```

   Check: the `Url` output and the health answer are as shown (the containers come back by themselves after the restart). Undo: create and execute the same change set with `DomainName` set back to `fernslop.example.com`.

   **9e. CI.** Set the `development` environment's `PUBLIC_URL` variable to `https://dev-fernslop.example.com`: `deploy-dev` polls it, and would otherwise check prod. Check: the variable shows the new value. Undo: set it back. The freeze is over: pushes to `main` and promotion are allowed again.

10. **Delete every copy of the dump.** The dump holds follower emails and photos. Do this last, once prod is confirmed. On dev: `rm -f /root/cutover.dump`. On your machine: `aws s3 rm "s3://$BUCKET/$KEY"`, and delete any local copy and the two counts files (`rm -f "${TMPDIR:-/tmp}"/dev-counts.txt "${TMPDIR:-/tmp}"/prod-counts.txt`). Prod's bucket would drop the object itself after 30 days, but do not wait.

    Check: `ls /root/cutover.dump` on dev says `No such file`, and `aws s3 ls "s3://$BUCKET/db/"` no longer lists `cutover-...dump`. Undo: none; the data is still in prod, and dev's database is still intact.

After step 10, the first run of `promote.yaml` ([promote to prod](#promote-to-prod)) comes only after prod passed steps 7 and 8, and needs one successful `deploy-dev` first, so that the `deployed-dev` tag exists: merge the next change to `main`, wait for CI to go green and check `git ls-remote --tags origin deployed-dev` prints a commit ([#238](../backlog/done/238-env-ci-build-and-deploy-dev.md), [#239](../backlog/done/239-env-ci-promote-to-prod.md)). Then run "Promote to prod".

Dev now holds a copy of the real data, including follower emails and photos, and gets every push. Anonymising it is [#241](../backlog/parked/241-env-dev-data-scrub.md). It has no nightly backups: they come with a rebuilt dev instance, [#242](../backlog/parked/242-env-dev-backups.md).

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
