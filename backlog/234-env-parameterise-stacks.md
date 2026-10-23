# [env] Parameterise the stacks by app prefix, environment and domain
**What:** `infra/ec2-stack.yaml`, `ecr-stack.yaml` and `deploy.sh` take prefix (default `fernslop`), environment (`dev`/`prod`) and domain as inputs instead of hardcoding names, and tag every resource with them.
**Why:** The user wants a second (prod) copy next to today's stacks (now dev), and a forkable repo with its own prefix and URL.
**Edge cases:** Dev must resolve to today's live names (a change set the user runs shows no replacement); prod names must not match dev's `fernslop-*` wildcards; the backup metric needs an environment dimension; app-level names are [#240](parked/240-env-app-level-naming.md).
