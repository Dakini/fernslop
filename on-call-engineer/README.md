# On-call engineer

`oncall.py` polls Grafana's alert API every minute. Each new firing alert goes to a headless coding agent
(`claude -p` by default), which looks into it and, where a change in this repo fixes it, makes that change.

```sh
uv run --script on-call-engineer/oncall.py                # poll every minute until Ctrl-C
uv run --script on-call-engineer/oncall.py --once         # poll once
uv run --script on-call-engineer/oncall.py --dry-run      # print the agent prompt, start no agent
```

No dependencies beyond Python 3.12. The agent CLI must be on `PATH` and logged in.

## What it does with an alert

1. It reads `GET /api/alertmanager/grafana/api/v2/alerts`: active alerts, without silenced or inhibited ones.
2. A firing it has not handled yet (fingerprint plus start time) gets a new git worktree under `worktrees/` on
   the branch `oncall/<fingerprint>-<time>`, made from the current `HEAD`. Your checkout is not touched.
3. The agent runs in that worktree with the alert as JSON. It is told to follow the runbook, run the backend
   tests and not commit.
4. Its report, the changed files and the alert are written to `runs/<fingerprint>-<time>.md`.

Review the branch and merge it, or delete it:
`git worktree remove on-call-engineer/worktrees/<name> && git branch -D oncall/<name>`.

Agents run one at a time, and polling waits while one runs. Alerts that fire meanwhile are picked up on the next
poll. An agent run is stopped after 30 minutes (`--agent-timeout`). Handled firings are kept in `state.json`, so
a restart does not start them again. A firing is marked handled before its agent starts, so a crash is not
retried every minute. To run it again, delete its line from `state.json`.

## What the agent may do

Alert labels and annotations can hold text typed by the public. For example, `search_term` is whatever someone
typed into the plant search. So the prompt marks the alert as data, and the agent is limited to:

- Read, Grep, Glob, Edit, Write inside its worktree
- `uv run pytest` (as `cd backend && uv run pytest` too)

It has no network tools and no other shell commands, and it cannot commit or push (`--permission-mode dontAsk`
turns down anything else without asking). Keep it that way if you add tools. Always read its diff before you
merge.

## Settings

| Setting | Default |
|---|---|
| `GRAFANA_URL` or `--grafana-url` | `http://localhost:3000` (local Grafana needs no login) |
| `GRAFANA_TOKEN` | Grafana service account token (Viewer role is enough), for the server |
| `GRAFANA_USER`, `GRAFANA_PASSWORD` | Basic auth instead of a token |
| `ONCALL_AGENT` or `--agent` | `claude` |
| `--interval` | 60 seconds |
| `--agent-timeout` | 1800 seconds |

`state.json`, `runs/` and `worktrees/` are not checked in.
