# [api] Follow-up: weekly digest email job

## Goal

A command a scheduler can run weekly (`uv run python -m app.digest`) emails each follower of a room with activity a summary of it, with their unsubscribe link. It sends through an `EmailSender` interface whose default is a console/in-memory fake, so no email account is needed.

## Acceptance criteria

- [ ] `build_digests(store, now)` is a pure function (no sending, no clock reads) returning one digest per follow: recipient email, subject, plain-text body, one room each. A room with no follows gives none.
- [ ] A room counts as active if it has a feed event not undone with `created_at` in the 7 days up to `now` (a 6-day-old event counts, an 8-day-old one does not). Inactive rooms give no digest, whatever their `last_activity_at`.
- [ ] The body names the room and lists the text of those events (`FeedEvent.text`, newest first). Undone events never appear, and a room whose only recent events are undone gets no digest.
- [ ] Each body ends with `<base>/unsubscribe?token=<that follow's unsubscribe_token>`, where `<base>` is env `FERNSLOP_PUBLIC_URL` (default `http://localhost:5173`, trailing `/` stripped). Two followers get two different links.
- [ ] `EmailSender` is a small interface (`send(to, subject, body)`). `ConsoleSender` prints each message; `InMemorySender` records them for tests. The default sender is `ConsoleSender`, and `uv run python -m app.digest` runs `build_digests` on the store with `timestamps.now()` and sends each digest.
- [ ] If one send raises, the others are still sent, the run reports how many sent and failed, and the failure is not silent.
- [ ] `uv run pytest` passes, with tests per criterion using a fresh `Store` and `InMemorySender` (no real clock, no network). The unsubscribe token must not appear in logs or the console output beyond the link itself.

## Out of scope

- A real SMTP/provider sender: [#110](110-api-email-sender.md). A frontend page behind the unsubscribe link: [#111](111-api-unsubscribe-page.md). Running the scheduler (cron setup) and persisting follows across restarts: [#015](015-api-persistence.md).

## Constraints

- Code in `backend/app/digest.py` (with `__main__` support), tests in `backend/app/test_digest.py`. Use only `StoreProtocol` methods and `app.timestamps`. No new dependencies and no scheduler library. Follow `_docs/testing-guidelines.md`. Spec: the follow and unsubscribe notes in `openapi.yaml`.

## Original request
**What:** A scheduled job that emails each follower a summary of rooms that had activity that week, including the unsubscribe token link.
**Why:** This was moved out of 010. The spec says it is a scheduled job, not an endpoint, and it needs an email provider.
**Edge cases:** Rooms with no activity that week get no email. The digest must not include undone events.

## Comments

Software Engineer: Implemented in `backend/app/digest.py` (`build_digests`, `EmailSender`, `ConsoleSender`, `InMemorySender`, `send_digests`/`run`, `main`) with 22 tests in `backend/app/test_digest.py`; full suite passes. Notes: the 7-day window is `now-7d <= created_at <= now` (future events excluded). Failed sends are logged at ERROR with the recipient and exception type only (no message/body, so no token) and counted; `main` prints `Digests sent: N, failed: M` and exits 1 if any failed. `uv run python -m app.digest` uses the in-memory seeded store, so it currently sends nothing until follows exist (persistence is #015).

## QA: PASS

- [x] `build_digests(store, now)` is pure, one digest per follow (recipient, subject, plain-text body, one room); room with no follows gives none - PASS
      Scratch script: store unchanged after call, `timestamps.now` patched to raise was never hit, 2 followers gave 2 digests, no-follow room gave none
- [x] 7-day window; inactive rooms give no digest whatever `last_activity_at` - PASS
      6-day event counts; 8-day and 7d+1s events excluded; room with fresh `last_activity_at` but only 8-day event gave none (exactly 7d is included, future events excluded)
- [x] Body names room, lists `FeedEvent.text` newest first; undone events never appear; only-undone room gets no digest - PASS
- [x] Body ends with `<base>/unsubscribe?token=<token>`, `FERNSLOP_PUBLIC_URL` with default and trailing `/` stripped; distinct links per follower - PASS
      Checked default, `https://x.org/`, `https://x.org///`, and empty env
- [x] `EmailSender` / `ConsoleSender` / `InMemorySender`; `python -m app.digest` uses `ConsoleSender` and `timestamps.now()` - PASS
      `uv run python -m app.digest` ran, printed `Digests sent: 0, failed: 0`, exit 0 (seeded store has no follows)
- [x] One failing send does not stop the others; counts reported; failure not silent - PASS
      Failing recipient raising with the body in its message: other 3 sent, report sent=3 failed=1, ERROR log has recipient + exception type only; `main()` printed `Digests sent: 3, failed: 1` and exited 1 (0 when none failed)
- [x] Tests per criterion; token not in logs/console beyond the link - PASS
      Token appears once in console output (the link) and never in log output

Tests: `uv run pytest`, 705 passed, 0 failed (`app/test_digest.py`: 22 passed). Also ran my own script exercising the cases above.
