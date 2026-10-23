# [qa] design-check skill points at the rewritten design system doc

## Goal

Section 1 of `.claude/skills/design-check/SKILL.md` describes `_docs/design-system.md` as it is after #221: it documents the React, Tailwind and shadcn frontend. Today the section still calls it the older Django-template approach. Small, docs only: the engineer edits it and the orchestrator checks.

## Acceptance criteria

- [ ] Section 1 no longer mentions Django or calls the doc old. It says to read `_docs/design-system.md` first for tokens, components and layout rules.
- [ ] Section 1 keeps both of these: `styles.css` and `components/ui/` are the source of truth, and when the doc and the code disagree, the report says so. The doc itself says the code wins.

## Constraints

- Change only section 1 of `.claude/skills/design-check/SKILL.md`. No tests.
