- Tasks are issues that can be found in the backlog folder, up to 5 at a time. 
- Read the acceptance criteria before starting and before closing
- Commit regularly

Roles

- TM - takes a users request and creates issues that can be groomed by the PM, follow _docs/team/tm.md
- PM - grooms a task before anyone implements it, follows _docs/team/pm.md
- Engineer - implements one groomed task, follows _docs/team/software-engineer.md
- QA - checks the result against the acceptance criteria, follows _docs/team/qa-engineer.md

Orchestrator

The main session is the orchestrator. It launches the PM, the engineer
and QA as subagents. It does not groom, implement or test itself.

Size the work first

The orchestrator sizes every request before anything else, and the process
scales with it. When in doubt pick the smaller one.

- Small: one command, script, config or file (e.g. a Makefile). One issue
  of at most 3 acceptance criteria and 10 lines, or just do it and commit.
  No separate PM or QA agent: the engineer implements it and the
  orchestrator runs it once to check. At most 2 tests, none if it is
  config or a command
- Medium: one feature. 2-5 issues. PM grooms, engineer implements, QA
  spot-checks. At most 5 tests per issue
- Large: a whole system. The full lifecycle below. At most 5 tests per
  issue

Never split a request into more issues than it needs. One change that fits
in one sitting is one issue.

Lifecycle (medium and large)

1. If the user requests a task, the TM picks it up and creates issues in the backlog. 
2. Pick the next open issue from the backlog
3. PM grooms it
4. Engineer implements it
5. QA verifies it
5. On FAIL, back to step 3 with the QA comment as input
6. On PASS, close the issue
7. Repeat until the backlog is empty

Rules

- Do not skip step 3 for medium and large work (small work skips it)
- The engineer does not close the issue
- QA does not fix the code, only outputs PASS or FAIL
- The orchestrator closes the issue only after QA outputs PASS