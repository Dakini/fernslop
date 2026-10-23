# [qa] design-check skill points at the rewritten design system doc

## Goal

Section 1 of `.claude/skills/design-check/SKILL.md` describes `_docs/design-system.md` as it is after #221: it documents the React, Tailwind and shadcn frontend. Today the section still calls it the older Django-template approach. Small, docs only: the engineer edits it and the orchestrator checks.

## Acceptance criteria

- [ ] Section 1 no longer mentions Django or calls the doc old. It says to read `_docs/design-system.md` first for tokens, components and layout rules.
- [ ] Section 1 keeps both of these: `styles.css` and `components/ui/` are the source of truth, and when the doc and the code disagree, the report says so. The doc itself says the code wins.

## Constraints

- Change only section 1 of `.claude/skills/design-check/SKILL.md`. No tests.

## Engineer:

Rewrote section 1 of `.claude/skills/design-check/SKILL.md`. The Django line is gone. The first bullet now says to read `_docs/design-system.md` first, because it describes the React, Tailwind and shadcn frontend: tokens, components and layout rules. The second bullet keeps `styles.css` and `components/ui/` as the source of truth, notes that the doc itself says the code wins, and keeps the instruction to report any disagreement between doc and code. The third bullet (issue acceptance criteria) is unchanged. `grep -ni django .claude/skills/design-check/SKILL.md` returns nothing. Docs only, so no tests.
