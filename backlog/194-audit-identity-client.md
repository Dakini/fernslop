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

## Comments

**Engineer:** Implemented in `frontend/src/lib/identity.ts`, its test and the nickname form in `frontend/src/routes/r.$roomId.tsx`.
- `nicknameError` holds the backend rules (trimmed, 1–40 code points, no Cc/Cf/Zl/Zp except U+200D; lone surrogates rejected too since `encodeURIComponent` throws on them). Device id: trimmed, 1–64 code points.
- `loadIdentity` repairs non-JSON, non-object or bad `name`/`device_id`, keeps the valid half, generates the other and saves it. If localStorage get or set throws, an in-memory identity is used for the session and nickname changes update it.
- Nickname form: invalid name shows an inline `role="alert"` message under the field (same pattern as the Follow form), no save, no toast; empty keeps the old name as before. Removed `maxLength={40}` (it counted UTF-16 units, blocking 40 × 🌱) and the `slice(0, 40)` that could split a surrogate pair.
- Tests: 3 new in `identity.test.ts` (repair keeps valid half, bad nickname rejected, emoji accepted). They use a stubbed in-memory localStorage because Node 26's own `localStorage` global shadows jsdom's. `npm test`: 8 files, 44 tests pass.

## QA: PASS

- [x] `loadIdentity` repairs a broken stored value, keeps the valid half, saves it, headers never carry `undefined` - PASS
      Seeded `not json`, `[1,2]`, `42`, `null`, blank/missing/65-char/numeric `device_id` (with name "Bob"), and blank/numeric/41-char/U+202E/newline `name` (with `device_id` "dev-keep"), then loaded a room and posted. Each time the broken half was regenerated, the valid half kept, the repair saved to localStorage, and the POST went out with real `X-Device-Id`/`X-Actor-Name` values (201). A valid stored identity was left untouched
- [x] Rules match the backend, one helper in `frontend/src/lib/` - PASS
      `frontend/src/lib/identity.ts` (`nicknameError`, `cleanDeviceId`): trimmed, 1-40 code points, Cc/Cf/Zl/Zp rejected except U+200D, device id 1-64. Matches `auth.py`/`text.py`
- [x] Nickname form rejects control/format characters and over 40 characters inline, no save, no toast; empty keeps the old name - PASS
      U+202E (set and typed), tab, U+0007, U+2028, 41 × "x" and 41 × 🌱 each showed the message under the field, storage unchanged, no new "Nickname saved" toast. Empty and blank kept the old name. A newline cannot reach the field: the browser strips it from a text input on paste, so nothing invalid is saved
- [x] Emoji nicknames accepted and never cut - PASS
      👩‍🌾 and 40 × 🌱 were saved whole; a post with the 40 × 🌱 name sent a well-formed encoded header and got 201
- [x] localStorage unavailable: one identity for the session, nickname change works, nothing throws - PASS
      With `Storage.prototype.getItem`/`setItem` throwing: page loaded, two posts used the same device id, the nickname change to "Private Pat" showed in the chip and on the second post, no page errors
- [x] Tests in `frontend/src/lib/identity.test.ts` - PASS
      Three new tests: repair keeps the valid half, bad nickname rejected, emoji accepted

Tests: `cd frontend && npm test`, 8 files, 44 passed, 0 failed. Browser checks: Playwright against a static build served by this worktree's backend on port 8194
