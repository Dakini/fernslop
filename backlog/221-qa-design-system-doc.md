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

## QA: PASS

- [x] No Django/htmx/base templates/`_docs/outdated/`; every named thing exists - PASS
      `grep -niE 'django|htmx|template|outdated' _docs/design-system.md` returns nothing. All 7 `components/garden` components and their extra exports (`CARE_ICONS`, `shareUrl`, `copyShare`) exist. All 10 listed `components/ui` files are the only ones imported by `routes/` and `components/garden/`.
- [x] Tokens: colour, radius, font tokens from `styles.css` (light and dark), and the rule to use them - PASS
      Palette (moss, sage, cream, oat, terracotta, clay, soil, pond, all oklch), semantic mappings (background=cream, card=oat, primary=moss, secondary=sage, accent=clay, ring=sage), `--radius: 1.25rem` and the sm..3xl calc scale, Nunito / Nunito Sans, `shadow-soft` / `shadow-token`, base h1-h4 (display, 800, moss), reduced-motion and `animate-bob` all match `styles.css`. No raw hex/oklch/`[#` in `routes/` or `components/garden/`, so the rule is followed.
      Dark: `styles.css` has only `@custom-variant dark`, with no dark values, and nothing in app code sets `.dark` or uses `dark:`. The criterion asks the doc to record the tokens that exist, and a doc that invented a dark palette would break the first criterion ("every token named exists"). The doc says plainly that there is no dark mode and that no `dark:` classes should be added. That meets the intent.
- [x] Components: `components/ui` first (`components.json`), Button variants/sizes in use, dialogs, toasts, inputs, `components/garden/` - PASS
      `components.json`: style new-york, lucide. `button.tsx` defines the variants and sizes as documented. Variants in use: outline 6, soft 4, secondary 3, fab 1, plus the implicit default. Sizes in use: sm 8, lg 4, icon 1, fab 1, plus the implicit default. ghost, destructive and link are unused, as the doc says. `DialogContent className="rounded-3xl bg-oat sm:max-w-md"` and `DialogTitle font-display text-moss` match in CreateRoomDialog and AddPlantDialog. DeleteGardenDialog has `w-[calc(100%-2rem)] rounded-3xl bg-cream` and a `bg-terracotta` action. `PopoverContent className="rounded-2xl bg-cream"` (x2). Errors use `role="alert"` with `text-xs` (and `text-sm` in CreateRoomDialog). There is one `<Toaster position="top-center" />` in `__root.tsx`, and code calls only `toast.success` / `toast.error`.
- [x] Layout: `__root.tsx` shell, gutters, headings, mobile rules, `design-check` pointer - PASS
      `__root.tsx` has `lang="en"`, the viewport meta, the Google Fonts link, `QueryClientProvider`, `<Outlet />` and the Toaster. All 4 `<main>` elements are `mx-auto ... px-4` with the documented widths (`max-w-6xl py-8 md:py-14`, `max-w-7xl py-5 pb-28`, `max-w-md py-14 text-center`). h1 sizes match (`text-4xl md:text-5xl`, `text-3xl md:text-4xl`, `text-2xl`). The FAB is `fixed right-5 bottom-5`, and `h-11 sm:h-9` is in DeleteGardenDialog. The grids (`sm:grid-cols-2 lg:grid-cols-3`, `lg:grid-cols-[1fr_380px]`) and the Sprout kicker (`font-display font-bold text-sage`) match. The design-check details (mock app, 320/390/768/1280, overflow, tap targets, input size, off-token colours, `tmp/design-check/`) match `SKILL.md` and `design_audit.py`.

Tests: none run. The change is docs only (`git diff --stat 4242d24 HEAD`: `_docs/design-system.md` and this issue file). Checked with about 20 grep spot-checks against `frontend/src`.

Observations (not failures):
- The doc says the root error/not-found pages have "`h1`, muted text, a primary and an outline action". That is exact for the error page. The 404 page has an `h1` "404" plus an `h2` and only one primary link. Both pages use raw `rounded-md` button-like classes, not `Button`.
- "`Input` is `rounded-full`, `Textarea` `rounded-2xl`" comes from the classes at each call site. `components/ui/input.tsx` and `textarea.tsx` themselves are still `rounded-md`.
- `.claude/skills/design-check/SKILL.md` section 1 still says `_docs/design-system.md` "describes the older Django-template approach". That is stale now and is worth a small follow-up (out of scope here).
