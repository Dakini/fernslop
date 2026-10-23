#!/usr/bin/env bash
# Print "<table> <row count>" for every table in an instance's compose db, sorted by table name, so that
#   diff <(infra/table-counts.sh dev) <(infra/table-counts.sh prod)
# shows whether two databases hold the same data. Read-only: it runs one SELECT (psql in the compose db
# container) through SSM Run Command and prints no row contents. Needs operator credentials.
# Usage: infra/table-counts.sh <dev|prod>     (APP_PREFIX as for deploy.sh, default fernslop)
set -euo pipefail

USAGE="Usage: infra/table-counts.sh <dev|prod>"
ENVIRONMENT="${1:-}"
case "$ENVIRONMENT" in
  dev | prod) ;;
  "") echo "Missing environment. $USAGE" >&2; exit 1 ;;
  *) echo "Unknown environment '$ENVIRONMENT': use dev or prod" >&2; exit 1 ;;
esac
[ -z "${2:-}" ] || { echo "$USAGE" >&2; exit 1; }
PREFIX="${APP_PREFIX:-fernslop}"
if ! [[ "$PREFIX" =~ ^[a-z0-9-]+$ ]]; then
  echo "APP_PREFIX '$PREFIX' must be lowercase letters, digits and hyphens only" >&2
  exit 1
fi
if [ "$ENVIRONMENT" = prod ]; then STACK="prod-$PREFIX"; else STACK="$PREFIX"; fi

# Exact counts in one statement: query_to_xml runs a count(*) per table
SQL="select table_name, (xpath('/row/c/text()', query_to_xml(format('select count(*) as c from %I.%I', table_schema, table_name), false, true, '')))[1]::text from information_schema.tables where table_schema = 'public' and table_type = 'BASE TABLE' order by table_name;"
# base64 keeps the SQL's quotes out of the JSON and the shell on the way to the instance
SQL_B64=$(printf '%s' "$SQL" | base64 | tr -d '\n')

INSTANCE=$(aws cloudformation describe-stacks --stack-name "$STACK" \
  --query "Stacks[0].Outputs[?OutputKey=='InstanceId'].OutputValue" --output text)
if [ -z "$INSTANCE" ] || [ "$INSTANCE" = "None" ]; then
  echo "Stack $STACK has no InstanceId output" >&2
  exit 1
fi

CMD=$(aws ssm send-command --instance-ids "$INSTANCE" --document-name AWS-RunShellScript \
  --parameters "{\"commands\":[\"cd /opt/app\",\"echo $SQL_B64 | base64 -d | docker compose exec -T db psql -U fernslop -d fernslop -v ON_ERROR_STOP=1 -At -F ' '\"]}" \
  --query Command.CommandId --output text)
aws ssm wait command-executed --command-id "$CMD" --instance-id "$INSTANCE" >/dev/null 2>&1 || true
STATUS=$(aws ssm get-command-invocation --command-id "$CMD" --instance-id "$INSTANCE" --query Status --output text)
if [ "$STATUS" != Success ]; then
  echo "Counting on $INSTANCE ($STACK) finished with status $STATUS:" >&2
  aws ssm get-command-invocation --command-id "$CMD" --instance-id "$INSTANCE" \
    --query StandardErrorContent --output text >&2 || true
  exit 1
fi
aws ssm get-command-invocation --command-id "$CMD" --instance-id "$INSTANCE" \
  --query StandardOutputContent --output text | sed '/^$/d'
