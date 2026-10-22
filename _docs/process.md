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

Lifecycle

1. If the user requests a task, the TM picks it up and creates issues in the backlog. 
2. Pick the next open issue from the backlog
3. PM grooms it
4. Engineer implements it
5. QA verifies it
5. On FAIL, back to step 3 with the QA comment as input
6. On PASS, close the issue
7. Repeat until the backlog is empty

Rules

- Do not skip step 3
- The engineer does not close the issue
- QA does not fix the code, only outputs PASS or FAIL
- The orchestrator closes the issue only after QA outputs PASS