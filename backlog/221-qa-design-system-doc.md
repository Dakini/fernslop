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

## Comments

**Engineer:** Rewrote `_docs/design-system.md` (121 lines) from the code in `frontend/src`. All Django, htmx, base-template and `_docs/outdated/` content is gone. It now covers: the tokens in `styles.css` (palette, semantic shadcn colours, radius scale and which radius goes where, Nunito / Nunito Sans, `shadow-soft` / `shadow-token`, base heading styles, reduced motion) and the rule to use the token classes, not raw colours. Components: `components/ui` first (shadcn new-york, `components.json`), listing only the ones the app imports; the `Button` variants in use (`default`, `secondary`, `outline`, `soft`, `fab`) and sizes (`default`, `sm`, `lg`, `icon`, `fab`); Dialog, AlertDialog, Sheet and Popover patterns; inputs and labels with errors; toasts, including the RateLimitError rule; the seven `components/garden` components. Layout: the `__root.tsx` shell, the `px-4` gutter and page widths, heading sizes, mobile rules (375 px with no overflow, 24/44 px tap targets, dialog margins, FAB padding), and a pointer to the `design-check` skill.
Note on the "light and dark" criterion: `styles.css` has no dark token values. It only declares a `dark` variant, and nothing sets `.dark`. So the doc says there is no dark mode and that app code should not add `dark:` classes. It doesn't invent a dark palette. Docs only, so no tests.
