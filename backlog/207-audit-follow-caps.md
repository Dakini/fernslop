# [audit] Cap follow requests per address and purge stale unconfirmed follows

## Goal

One address cannot be sent a stream of confirmation emails, even from many IPs, and follows never confirmed are deleted after their 7-day window from #200 (`audit.md` 3, last fix bullet). Per-IP limits (follow 10/hour) are already in #195.

## Acceptance criteria

- [ ] Every `followRoom` request that passes validation counts as an attempt for its address, whatever happens next (new follow, re-sent confirmation, already confirmed so nothing sent).
- [ ] A 4th attempt for the same address (case-insensitive) within 24 hours, across all rooms, answers 429 with an `Error` body and `Retry-After` (seconds until its oldest counted attempt is 24 hours old), sends nothing and changes nothing. Another address is unaffected.
- [ ] The 429 is identical whether the address never followed, is unconfirmed or is confirmed, so the cap reveals nothing #200 hides.
- [ ] `python -m app.room_purge` also deletes follows still unconfirmed more than 7 days after their `created_at` and prints how many; confirmed and younger follows stay. The existing daily timer (#198) runs it.
- [ ] `openapi.yaml` `followRoom` documents the cap; the mock service never caps.
- [ ] Tests: the 4th attempt across two rooms is 429 with nothing sent, also for a confirmed address; the purge removes only expired unconfirmed follows.

## Out of scope

- A per-room cap: not planned (20 requests would lock a garden's follow form for everyone for a day); see the open question below.
- The browser's wording for long waits (`Try again in N hours`): [#214](214-audit-rate-limit-double-toast.md).
- A real sender: [parked #110](parked/110-api-email-sender.md).

## Constraints

- `backend/app/routers/follows.py`, `models.py` (attempt times in `StoredFollow`'s JSON, pruned to 24 hours), `store.py`/`sql_store.py` (follows by `email_key`), `room_purge.py`, `openapi.yaml`, `test_follows.py`. No new SQL column (parked [#140](parked/140-db-migrations.md)). At most 3 tests.
- Attempts are recorded in the same transaction that reads them, so parallel requests cannot all slip under the cap.

**Open question (user):** keep the PM default of 3 attempts per address per 24 hours and no per-room cap?

**Engineer:** Implemented with the confirmed cap: 3 requests per address per 24 hours across all rooms, with no per-room cap.
- `StoredFollow.attempts` (a JSON list with a default, so no SQL column) records each request's time, pruned to 24 hours when the follow is saved. `followRoom` reads every follow of the address (new `list_follows_by_email`, matched on `email_key`) inside the same transaction that saves the attempt. A 4th request answers 429 with the same message and `Retry-After` format as the per-IP limit, sends nothing and writes nothing. A re-follow while unconfirmed still restarts the 7 days and re-sends the link. `FERNSLOP_RATE_LIMIT=off` also turns this cap off.
- `room_purge` also calls the new `purge_unconfirmed_follows` and prints `Purged N unconfirmed follow(s)`. It uses the 7-day `CONFIRM_WINDOW` and ignores `--days`. The existing daily timer already runs it.
- `openapi.yaml` `followRoom` documents the cap. The mock service needed no change because it never caps.
- Tests: the 4th request across two rooms gets a 429 with nothing sent or changed, checked both unconfirmed and confirmed (one parametrized test), while another address is unaffected. A second test checks the purge. I also changed one assertion in `test_room_delete.py`, which is outside the listed files: it compared every line the purge printed, so it had to filter to the room lines.
- Known gap: unsubscribing deletes the follow and its attempts, so an address that unsubscribes can follow 3 more times. Each follow needs a confirmation link, so this cannot be used to send a flood of emails.
- Checks: `uv run pytest` (169 passed, 2 skipped), `uvx ruff check .` passes, and `openapi.yaml` parses.

## QA: PASS

- [x] Every request that passes validation counts, whatever happens next - PASS
      Through TestClient (SQLite and a throwaway Postgres 16): 3 requests (new follow, re-send, request after confirming) all count. The 4th is 429 in each case. Re-following while unconfirmed re-sends the link and restarts `created_at`.
- [x] 4th request for an address within 24h, across all rooms and in any case, is 429 with `Error` + `Retry-After`; it sends nothing and changes nothing; another address is unaffected - PASS
      Requests at T0, T0+1h (`Ada@Example.com`) and T0+2h on 3 rooms, then the 4th at T0+3h (`ADA@EXAMPLE.COM`): 429 `{"message": "You're going a bit fast. Try again in 75600 seconds."}`, `Retry-After: 75600` (= 21h, expected). Nothing was sent and the follows' JSON was unchanged. `bob@example.com` got 201 at the same moment. At T0+24h+1s it was 201 again. `FERNSLOP_RATE_LIMIT=off`: 6 requests in a row, all 201. 8 parallel requests (threads + barrier) for one fresh address: exactly 3x201 and 5x429, 3 emails sent, 3 attempts stored, on both SQLite and Postgres.
- [x] The 429 is identical whether the address is unconfirmed, confirmed or brand new to the room - PASS
      Unconfirmed, confirmed, and a 4th request to a room the address never followed: all 429 with the same body and `Retry-After: 82800`. The brand-new case sent nothing and created no follow.
- [x] `python -m app.room_purge` deletes follows still unconfirmed more than 7 days after `created_at` and prints the count; the daily timer runs it - PASS
      Scratch SQLite with unconfirmed follows aged 8d, 7d+1m and 6d23h, plus a 30-day-old confirmed one. The purge printed `Purged 2 unconfirmed follow(s)`, and the 6d23h and confirmed follows remain. A second run (`--days 0`) printed 0. On Postgres: `Purged 1 unconfirmed follow(s)`, with the young and confirmed follows kept. `infra/ec2-stack.yaml` timer runs `fernslop-task@room_purge.service`.
- [x] `openapi.yaml` `followRoom` documents the cap; the mock never caps - PASS
      The description covers 3 requests per 24h per address (case-insensitive), all rooms, every state, the identical 429/`Retry-After`, no per-room cap and the purge. The YAML parses. In `frontend/src/services/mock/mockService.ts`, `followRoom` has no cap.
- [x] Tests: the 4th request across two rooms is 429 with nothing sent, also when confirmed; the purge removes only expired unconfirmed follows - PASS
      `test_fourth_follow_for_an_address_across_two_rooms_is_429_sends_nothing_and_changes_nothing` (parametrized: unconfirmed and confirmed) and `test_room_purge_deletes_only_follows_unconfirmed_after_7_days`.

Known gap (unsubscribing deletes the follow and its attempts, which resets the count): outside the criteria. Unsubscribing needs the token from an email the address received, so a third party cannot use it to flood an address. Not a FAIL.

Tests: `uv run pytest`, 169 passed, 2 skipped, 0 failed. `uvx ruff check .`: all checks passed. The Postgres checks ran against a throwaway container on port 55437, which has since been removed.
