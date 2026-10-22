# [audit] Validate the stored identity and nickname in the frontend

## Goal

The frontend never sends a broken identity and catches a nickname the backend would reject before saving it, so users no longer hit 400s the UI cannot explain (`audit.md` 14, first and second bullets).

## Acceptance criteria

- [ ] `loadIdentity` repairs a stored value that is not JSON, not an object, or has a missing, blank, non-string or too long `name` or `device_id`: it keeps the valid half (a broken `device_id` keeps the nickname, and the other way round), generates the other, saves the result, and the headers never carry `undefined`.
- [ ] The rules match the backend (`backend/app/auth.py`, `backend/app/text.py`): name trimmed, 1–40 characters counted as code points like Python `len`, no Cc/Cf/Zl/Zp except the zero-width joiner; device id 1–64 characters. One helper in `frontend/src/lib/` holds them.
- [ ] Nickname form (`frontend/src/routes/r.$roomId.tsx`): a name with a control or format character (a pasted newline, U+202E) or over 40 characters shows an inline message under the field, is not saved and shows no "Nickname saved" toast; an empty name keeps the old one, as today.
- [ ] Emoji nicknames (👩‍🌾, 40 × 🌱) are accepted and never cut in the middle of a character (today `slice(0, 40)` can leave a lone surrogate, which makes `encodeURIComponent` throw).
- [ ] With localStorage unavailable (get and set throw, e.g. private mode), one identity is used for the whole session, a nickname change works for the session, and nothing throws.
- [ ] Tests in `frontend/src/lib/identity.test.ts`: repair keeps the valid half; a bad nickname is rejected; emoji pass.

## Out of scope

- Nothing moved out of this issue.

## Constraints

- `frontend/src/lib/identity.ts`, its test, the nickname form in `frontend/src/routes/r.$roomId.tsx`. Inline message per `_docs/design-system.md`. No new dependency.
- After #193 (the backend rules it mirrors). At most 3 tests.
