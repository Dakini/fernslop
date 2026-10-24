# [otel] Infra: pass the environment name (dev/prod) to the running app container

## Goal

The app container on each server has `FERNSLOP_ENVIRONMENT` set to its stack's `Environment` (`dev` or `prod`), so [#243](243-otel-backend-sdk-and-resource.md) can report it. Existing servers pick it up without being rebuilt.

## Acceptance criteria

- [x] A newly created server writes `FERNSLOP_ENVIRONMENT=<Environment>` into `/opt/app/app.env` (UserData in `infra/ec2-stack.yaml`, next to `FERNSLOP_PUBLIC_URL`)
- [x] The deploy document (`DeployDocument`) also sets that line on every run, replacing any old one like it does `APP_TAG`, so a live server gets it on its next deploy once `infra/deploy.sh` has updated the stack
- [x] After `infra/deploy.sh dev <tag>`, `docker compose exec app printenv FERNSLOP_ENVIRONMENT` on the dev instance prints `dev`; on prod, `prod`. Running the deploy twice leaves exactly one such line in `app.env`
- [x] The image stays environment-neutral: `backend/Dockerfile` and `infra/build.sh` do not set `FERNSLOP_ENVIRONMENT`
- [x] `infra/README.md` says, generically (no real hosts, IPs or account ids), that the app gets `FERNSLOP_ENVIRONMENT` from the stack, and that servers created before this change need one `infra/deploy.sh <env> <tag>` run (it updates the deploy document) before the next CI deploy sets it
- [x] `aws cloudformation validate-template --template-body file://infra/ec2-stack.yaml` passes (or `cfn-lint` if installed)

## Out of scope

- Reading `FERNSLOP_ENVIRONMENT` in the app and the `local` fallback when unset: [#243](243-otel-backend-sdk-and-resource.md)
- Sending telemetry anywhere (OTLP settings): [#245](../parked/245-otel-export-to-collector.md)

## Constraints

- Change only `infra/ec2-stack.yaml` and `infra/README.md`; no backend code, no tests (config only)
- Keep the deploy document's `tag` parameter and `allowedPattern` unchanged; take the value from the stack's `Environment` parameter (`!Sub`), not a new SSM parameter, so CI and `promote.yaml` need no change
- Keep `app.env` mode 600 and keep the deploy document's `umask 077`
