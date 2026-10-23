# [ci] Follow-up: harden the GitHub deploy roles (concerns from #227 QA)
**What:** Stop the CloudFormation role from changing the backup bucket policy, and stop `AWS-RunShellScript` (root) from reaching the backups.
**Why:** QA on [#227](../done/227-ci-github-oidc-role.md); items 1 and 3 moved to [#236](../236-env-iam-split-per-environment.md) and item 4 to [#238](../238-env-ci-build-and-deploy-dev.md).
**Edge cases:** Changing the live `fernslop-github` stack is run by the user.
