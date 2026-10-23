# [env] Split the GitHub and CloudFormation roles per environment

## Goal

`infra/github-oidc-stack.yaml`, deployed once per environment, gives dev and prod their own deploy and CloudFormation roles that cannot reach the other environment, closes items 1 and 3 of [#233](parked/233-ci-deploy-iam-hardening.md), and lets only the prod role run the manual promotion (#239). The user applies it live.

## Acceptance criteria

- [ ] The template takes #234's prefix and environment (`dev`/`prod`). With dev values, the live `fernslop-github` stack keeps every logical ID and every property that would force a replacement, so its role ARNs stay valid. The OIDC provider gets `DeletionPolicy: Retain`
- [ ] The dev deploy role trusts only `repo:<repo>:ref:refs/heads/main`. The prod deploy role trusts only `repo:<repo>:environment:production`. `TrustSubject` is removed
- [ ] `aws iam simulate-custom-policy` on one environment's two role policies, run against the other environment's ARNs (stacks, roles, instance profile, backup bucket, log group, alarms, dashboard and its github stack), returns only denies. The one exception is that the prod deploy role has `ssm:GetParameter` on dev's `/<stack name>/deployed-tag` (#235)
- [ ] Each deploy role has `ssm:GetParameter` and `ssm:PutParameter` on its own environment's `/<stack name>/deployed-tag` and on no other parameter. Simulated: dev PutParameter on prod's parameter is denied, and prod PutParameter on dev's parameter is denied
- [ ] EC2 actions that change resources need the role's own environment tag on the resource and on the create request, and that tag can never be set to another value or removed. The deploy role's `ssm:SendCommand` reaches only instances carrying its own environment tag. Simulated: dev SendCommand, TerminateInstances and CreateTags against a prod-tagged instance are denied
- [ ] Each stack creates a permissions-boundary policy that allows only what `InstanceRole` uses today, plus `ssm:GetParameter` on its own `deployed-tag` parameter (#235). The CloudFormation role can create or change a role only when that boundary is attached, and cannot remove the boundary or edit it. `ec2-stack.yaml` sets the boundary on `InstanceRole` without replacing it
- [ ] Only the dev deploy role can upload image layers to the shared `fernslop` repo. The prod deploy role has `ecr:DescribeImages`, `ecr:BatchGetImage` and `ecr:PutImage`, so it can add `prod-<tag>` to an existing image, but it has no layer-upload actions. IAM cannot limit which tag is written, and the README says so. Neither role can change the `fernslop-ecr` stack, so a CI run can't delete prod's images
- [ ] The "GitHub Actions deploy role" section of `infra/README.md` gives the user the order to run things in: update `fernslop-github` through a change set and check that it shows no `Replacement`, create the prod stack with `CreateOidcProvider=false`, then update the ec2 stacks. It also says where the ARNs go: repo variables for dev, and variables with the same names on the `production` environment for prod. If those are missing, the prod job falls back to dev's ARNs, which cannot be assumed

## Out of scope

- #233 item 2 (the backup bucket policy, and root on the instance reaching the bucket) stays in [#233](parked/233-ci-deploy-iam-hardening.md). Item 4 is in [#238](238-env-ci-build-and-deploy-dev.md)
- Stack names, resource names and the environment tag: [#234](234-env-parameterise-stacks.md). Moving the ECR stack deploy out of CI, and tag immutability: [#235](235-env-build-and-deploy-by-tag.md)
- Workflows that assume these roles: [#238](238-env-ci-build-and-deploy-dev.md), [#239](239-env-ci-promote-to-prod.md). Creating prod and running the live updates: [#237](237-env-prod-stack-and-cutover.md) and the user

## Constraints

- Change only `infra/github-oidc-stack.yaml`, that README section, and the boundary on `InstanceRole` in `infra/ec2-stack.yaml`. Start after #234 is merged, because this work uses its names and tag key and edits the same file
- Nobody but the user writes to AWS. The engineer and QA may only run `aws cloudformation validate-template`, `aws iam simulate-custom-policy`, and `describe`/`get`/`list` calls. No new dependencies

**Orchestrator decisions:**
- Each deploy role may `ssm:GetParameter`/`PutParameter` only its own `/<stack name>/deployed-tag`. The prod role may also read dev's tag. Instance roles read their own tag at boot ([#235](235-env-build-and-deploy-by-tag.md)).
- The prod deploy role may also `ecr:BatchGetImage`/`ecr:PutImage`, but only to add `prod-<tag>` tags (#235).
- The `fernslop-ecr` stack is deployed by hand. Neither CI role may change it.
- Prod role ARNs go in the GitHub `production` environment, and dev's go in repo variables of the same name.
