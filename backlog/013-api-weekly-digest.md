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
