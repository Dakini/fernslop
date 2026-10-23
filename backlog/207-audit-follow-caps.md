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
