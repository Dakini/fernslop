# [audit] Double opt-in for follows and a safer digest email

## Goal

A follow gets digests only after the address owner clicks a confirmation link, the digest cannot pass user text off as the site's own lines, the follow response does not reveal who already follows, and tokens never reach server logs (`audit.md` 3 bullets 1–4 and the enumeration note, 10). Decision: follows that exist today count as unconfirmed (no real email has ever been sent, see parked [#110](parked/110-api-email-sender.md)); their owners follow again to get digests.

## Acceptance criteria

- [ ] `POST /rooms/{id}/follows` stores an unconfirmed follow and sends a confirmation email through an `EmailSender` dependency (`ConsoleSender` today) with the link `<FERNSLOP_PUBLIC_URL>/confirm-follow#token=…`. It always answers 201 with only `{room_id, email}` (no `id` or `created_at`, which would reveal an earlier follow); a repeat re-sends the email while unconfirmed and sends nothing once confirmed. The follow form then says to check the inbox.
- [ ] A new confirm call (e.g. `POST /api/follows/confirm` with `{"token"}`) sets `confirmed_at` and answers `{"confirmed": true}`, also when repeated; an unknown token, or a follow left unconfirmed for more than 7 days, answers `{"confirmed": false}` and changes nothing.
- [ ] A new `/confirm-follow` page reads the token from the URL fragment, calls confirm once (like `unsubscribe.tsx`, `ssr: false`), shows confirmed, expired-or-invalid and could-not-reach states, and never shows the email address. Styled per `_docs/design-system.md`.
- [ ] Only confirmed follows get digests. The subject is one line (control, format and separator characters become spaces); the body starts with the unsubscribe link, then each feed line as a `- ` bullet with further lines indented, so no user text starts a line of its own.
- [ ] Both links carry the token in the fragment (`/unsubscribe#token=…`), the unsubscribe page reads it there and still accepts the old `?token=` (done [#111](done/111-api-unsubscribe-page.md)), and no token shows up in the uvicorn access log while confirming or unsubscribing.
- [ ] Follows stored before this change (no `confirmed_at`) get no digest.
- [ ] `openapi.yaml` (`followRoom` 201 only and its new body, the confirm operation, the link formats), `GardenService`, the HTTP service and the mock agree.

## Out of scope

- Caps per room and per address per day, and purging expired unconfirmed follows: [#207](207-audit-follow-caps.md).
- A real sender with SPF/DKIM: [parked #110](parked/110-api-email-sender.md).

## Constraints

- `backend/app/routers/follows.py`, `models.py`, `digest.py`, `frontend/src/routes/` (new confirm route, `unsubscribe.tsx`, the follow form in `r.$roomId.tsx`), `frontend/src/services/`, `openapi.yaml`.
- `confirmed_at` is a pydantic field with default `None` in the JSON `json` column, not a SQL column (parked [#140](parked/140-db-migrations.md)). The email is sent after the transaction commits; a failed send is logged without the token and the follow still answers 201.
- `git stash show -p stash@{0}` ("wip: follow double opt-in + digest") is an unreviewed start (`confirmed_at`, `get_email_sender`, `one_line`, `_quoted`, fragment links; it reuses the unsubscribe token for confirmation, which is acceptable). Use or discard it; do not apply it unread.
- At most 5 tests.

## Comments

**Engineer:** Implemented in `b810a4e` (backend) and `a230df3` (frontend, `openapi.yaml`). I reviewed the stash and reused its `confirmed_at`, `get_email_sender`, `one_line`, fragment links and confirmation email, with two changes: `_bullet` splits with `splitlines()`, so `\r`, ` ` and similar breaks in old data are indented too, not only `\n`; and the room name appears only in the subject. Backend: `RoomFollow` is now `{room_id, email}`, and `StoredFollow` is its own model with `confirmed_at: Timestamp | None = None` in the JSON column (no store change). `POST /rooms/{id}/follows` always answers 201 `{room_id, email}`. A new or still-unconfirmed follow gets a confirmation email through the `get_email_sender` dependency after the transaction commits; a failed send is logged with the address and exception type only. A confirmed follow gets no email. Decision: a repeat while unconfirmed restarts the 7-day window (`created_at = now`) so the re-sent link works. Follows stored before this change get a working link the same way. New `POST /api/follows/confirm` (`confirmFollow`) answers `{"confirmed": true}`, also on repeat, or `false` for an unknown token or a follow left unconfirmed for more than 7 days, changing nothing. Digest: confirmed follows only. The subject goes through `one_line`. The body starts with the `/unsubscribe#token=` link, then each feed line as a `- ` bullet with further lines indented. Frontend: new `/confirm-follow` route (`ssr: false`, confirms once, shows confirmed, expired-or-invalid and couldn't-reach states, never shows the email). `unsubscribe.tsx` reads the token from the fragment and still accepts `?token=`. Both use the shared `routes/-token.ts`, which the route generator ignores; `routeTree.gen.ts` was regenerated. The follow popover now says to check the inbox. `GardenService.confirmFollow` is in the types, the HTTP service and the mock; the mock copies the 7-day window and its restart. `openapi.yaml`: `followRoom` answers 201 only with the new `RoomFollow`, `confirmFollow` is new, and the intro gives the token and link formats (`openapi-spec-validator`: OK). Manual check: I ran uvicorn on a scratch DB, followed, confirmed, requested `/confirm-follow#token=…` and `/unsubscribe#token=…`, then unsubscribed. 0 access-log lines contain the token. Tests (5 new or rewritten): in `test_follows.py`, the opt-in flow (same 201 body each time, two emails then none, confirm idempotent) and unknown/expired confirm, replacing the old 200-on-repeat tests; in `test_digest.py`, confirmed-only plus subject/body injection, with the existing digest tests updated to the fragment link and confirmed follows; `src/test/confirm-follow.test.tsx` for the page states; and `unsubscribe.test.tsx` for the fragment and query token. The mock follow test was updated for the new shape and `confirmFollow`. `uv run pytest`: 151 passed, 2 skipped. `uvx ruff check .`: clean. `npm test`: 43 passed. `tsc`: no errors in touched files (errors elsewhere were already there).

## QA: PASS

- [x] `POST /rooms/{id}/follows` stores an unconfirmed follow, sends a confirmation email via `EmailSender`, always 201 `{room_id, email}`, re-sends while unconfirmed, nothing once confirmed; form says check the inbox - PASS
      TestClient with an injected `InMemorySender`: first follow, repeat and post-confirm follow all 201 with exactly `{room_id, email}`; 2 emails while unconfirmed, none after confirming; link is `<FERNSLOP_PUBLIC_URL>/confirm-follow#token=…`. In the browser the popover shows "Check your inbox: …"
- [x] Confirm call sets `confirmed_at`, `{"confirmed": true}` also on repeat; unknown token or >7 days unconfirmed answers false and changes nothing - PASS
      Unknown token false; real token true twice, `confirmed_at` set; follow created 8 days ago false with `confirmed_at` still null; 6d23h old confirms
- [x] `/confirm-follow` page reads the fragment token, calls confirm once, shows confirmed / expired-or-invalid / could-not-reach, never shows the email, styled per design system - PASS
      Playwright on the static build served by the branch backend (port 8420): `#token=nope` shows expired-or-invalid, aborted request shows "We couldn't reach the garden", real token shows "You're following this garden" with exactly 1 confirm request and no email in the page; layout matches the unsubscribe page at 390px and 1280px
- [x] Only confirmed follows get digests; subject one line; body starts with the unsubscribe link, feed lines as `- ` bullets with further lines indented - PASS
      Room name and feed text with `\r\n`, U+202E, U+2028, U+0085 and a fake "To stop these emails…" line: subject has them as spaces on one line; body line 1 is the real unsubscribe link, the fake lines are indented under `- watered`; recipients were only the two confirmed follows (not an unconfirmed or a legacy one)
- [x] Both links carry the token in the fragment, unsubscribe page reads it there and still accepts `?token=`, no token in the uvicorn access log while confirming or unsubscribing - PASS
      Digest link is `/unsubscribe#token=…`; browser unsubscribe via `#token=` and via `?token=` both show "You're unsubscribed"; 76 access-log lines covering follow, confirm (x3) and fragment unsubscribe contain neither token (the legacy `?token=` URL is logged by nature, checked separately)
- [x] Follows stored before this change (no `confirmed_at`) get no digest - PASS
      Rewrote a stored follow's JSON without the `confirmed_at` key; it loads and gets no digest
- [x] `openapi.yaml`, `GardenService`, HTTP service and mock agree - PASS
      `followRoom` 201 only with `{room_id, email}`, new `confirmFollow` (`/follows/confirm`, `{token}` -> `{confirmed}`), fragment link formats documented; `confirmFollow` in types, `httpService.ts` and the mock (same 7-day window)

Tests: `cd backend && uv run pytest`, 151 passed, 2 skipped, 0 failed; `cd frontend && npm test`, 43 passed, 0 failed
