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
