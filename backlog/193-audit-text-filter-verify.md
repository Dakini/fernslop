# [audit] Verify control and format character filtering, and state the identity threat model

## Goal

Verify commit `79c90d5` (made outside the process; `audit.md` 3 filtering part and 11): user-written names, labels and post text reject control and format characters, and the docs say plainly that identity is self-asserted. The code is believed done; the engineer fills the gaps: tests for the allowed cases, `openapi.yaml` messages and the threat-model note.

## Acceptance criteria

- [ ] A Cc, Cf, Zl or Zp character (e.g. CRLF, U+202E, U+200B, U+2028) gives 400 and writes nothing in `X-Actor-Name`, room name, description and region, area label (add and rename) and post text; the message names the field (`Name contains invalid characters`, `An area label contains invalid characters`, `Text contains invalid characters`, `X-Actor-Name contains invalid characters.`, ...).
- [ ] These are accepted: 👩‍🌾 (ZWJ sequence), 👍🏽 (skin tone), 🇬🇧 (flag), accented and non-Latin letters. Post text keeps `\n` and `\t`, and `\r\n` or a lone `\r` is stored as `\n`.
- [ ] Rows stored before the filter (insert one with U+202E directly through the store) still load: `GET /api/rooms` and `GET /api/rooms/{id}` give 200, and moving such an area without sending `label` works.
- [ ] `openapi.yaml` lists the new 400 message on `createRoom`, `addArea`, `updateArea`, `postUpdate` and the actor headers.
- [ ] The Authentication section of `openapi.yaml` states the threat model in 2–4 sentences: names are self-asserted, anyone can post as "Ada", look-alike letters (Cyrillic "А") are not filtered, only control and format characters are.
- [ ] New tests: the emoji above are accepted; an area label with U+202E is rejected.

## Out of scope

- The same rules in the frontend: [#194](194-audit-identity-client.md).
- Escaping user text in the digest email: [#200](200-audit-follow-opt-in.md).
- Homoglyph filtering: decided against (names are self-asserted by design, audit 11); documented instead.

## Constraints

- Tests next to the code in `backend/app/`, and `openapi.yaml`. Change `text.py` only if a criterion fails. At most 2 new tests.

## Comments

**Engineer:** Verified `79c90d5`; every criterion holds, so `text.py` is unchanged. A throwaway script (not committed) checked CRLF/NUL, U+202E, U+200B and U+2028 against `X-Actor-Name`, room name/description/region, area label (add and rename) and post text: each gives 400 with the field-named message and writes nothing. 👩‍🌾, 👍🏽, 🇬🇧, accented, Cyrillic, CJK and Arabic text are accepted. Post text keeps `\n`/`\t` and stores `\r\n` and lone `\r` as `\n`. A room and area saved with U+202E straight through the store still load via `GET /api/rooms` and `GET /api/rooms/{id}` (200), and moving that area without `label` works. `openapi.yaml`: added a threat-model paragraph to Authentication. Listed the invalid-character 400 messages on `createRoom`, on `addArea`/`updateArea` (new shared `BadAreaRequest` response), on `postUpdate` and on the `X-Actor-Name` parameter. Two new tests: `test_post_accepts_emoji_and_non_latin_letters_in_name_and_text` (test_posts.py, parametrised) and `test_rename_area_to_a_label_with_a_right_to_left_override_returns_400_and_writes_nothing` (test_areas.py). `uv run pytest`: 140 passed, 2 skipped. `uvx ruff check .`: clean.
