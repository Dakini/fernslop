# [qa] Design system doc describes the Tailwind/shadcn frontend

## Goal

`_docs/design-system.md` describes the UI as it is built in `frontend/src` (React, TanStack Router, Tailwind, shadcn/ui), not Django templates and htmx, so anyone touching the UI follows the real components and tokens. Medium (docs only).

## Acceptance criteria

- [ ] No mention of Django templates, htmx, base templates or `_docs/outdated/`; every file, component, variant and token named exists in `frontend/src`.
- [ ] Tokens: the colour, radius and font tokens from `frontend/src/styles.css` (light and dark), and the rule to use them instead of raw colours.
- [ ] Components: use `components/ui/*` (shadcn, `components.json`) first; the `Button` variants and sizes in use, dialogs, toasts, inputs; app components in `components/garden/`.
- [ ] Layout: the page shell in `routes/__root.tsx`, gutters and headings as used, and mobile rules (no horizontal overflow at 375 px, tap targets), pointing to the `design-check` skill for screenshot checks.

## Out of scope

- Changing any component or style to match the doc.

## Constraints

- `_docs/design-system.md` only, under about 120 lines. Describe what is used, not every shadcn file present. No tests.
