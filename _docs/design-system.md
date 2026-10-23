# Design system

How the UI in `frontend/src` is built: React, TanStack Router (file routes in
`src/routes/`), Tailwind CSS v4 and shadcn/ui. Read this before touching the
UI. It describes what the code does today; when they disagree, the code wins.

## Tokens (`frontend/src/styles.css`)

All colours, radii, fonts and shadows are CSS variables in `:root`, exposed to
Tailwind by `@theme inline`. Use the Tailwind classes they create
(`bg-oat`, `text-moss`, `rounded-3xl`, `shadow-soft`, `font-display`). Do not
write raw colours (hex, `rgb()`, `oklch()`) or arbitrary values like
`bg-[#...]` in components; add or change a token in `styles.css` instead.

- **Palette:** `moss`, `sage`, `cream`, `oat`, `terracotta`, `clay`, `soil`,
  `pond` (all `oklch`).
- **Semantic (shadcn) colours:** `background` (cream), `foreground` (dark
  moss), `card` (oat), `popover` (cream), `primary` (moss), `secondary` (sage),
  `muted` / `muted-foreground`, `accent` (clay), `destructive`, `border`,
  `input`, `ring` (sage), each with its `-foreground` pair. `chart-1..5` and
  `sidebar-*` exist but are not used by app screens.
- **Radius:** `--radius: 1.25rem`; `rounded-sm` to `rounded-3xl` are derived
  from it (`lg` = the base, `3xl` = base + 12px). Buttons, pills and inputs
  are `rounded-full`; cards, panels and dialogs are `rounded-3xl`; list rows
  `rounded-2xl`; photos `rounded-xl`.
- **Fonts:** `font-display` = Nunito (headings, buttons, labels on the
  canvas), `font-sans` = Nunito Sans (body, set on `body`). Both are loaded
  from Google Fonts in `__root.tsx`.
- **Shadows:** `shadow-soft` (cards, panels, the FAB) and `shadow-token`
  (plant pins on the canvas), both tinted with moss.
- **Base styles:** `h1`-`h4` are `font-display`, weight 800, colour moss, so
  headings need only a size class. `prefers-reduced-motion` turns off all
  animation and transitions. `animate-bob` is the one custom animation.
- **Dark mode:** none. `styles.css` declares a `dark` variant but no dark
  token values, and nothing sets `.dark`. Don't add `dark:` classes in app code.

## Components

**Use `components/ui/*` first.** These are shadcn/ui ("new-york" style, lucide
icons, configured in `frontend/components.json`), edited to match the tokens.
Many files are present; the app uses these: `button`, `input`, `textarea`,
`label`, `dialog`, `alert-dialog`, `sheet`, `popover`, `tabs`, `sonner`.

**`Button`** (`components/ui/button.tsx`) is `rounded-full`, bold
`font-display`, and every icon child is `size-4`. Variants in use:

| Variant | Look | Used for |
|---|---|---|
| `default` | moss on cream | main action of a form or page (Create, Post, Save) |
| `secondary` | sage | secondary actions (Share, Rename, care buttons, Load older) |
| `outline` | bordered cream | quiet or destructive-ish actions (Remove plant, Delete area, Visit the gardens) |
| `soft` | oat with moss text | toolbar / "more" actions (Add area, Follow, Show more gardens) |
| `fab` | terracotta, `shadow-soft` | the floating Add plant button; also an overdue care action |

Sizes in use: `default` (h-9), `sm` (h-8, text-xs), `lg` (h-11, page-level
calls to action), `icon` (9x9), `fab` (16x16). `ghost`, `destructive` and
`link` exist but app code does not use them. Use `<Button asChild>` around a
router `Link` for link buttons.

**Dialogs:** `Dialog` for forms (`DialogContent className="rounded-3xl bg-oat
sm:max-w-md"`, `DialogTitle` in `font-display text-moss`, plus a
`DialogDescription`). `AlertDialog` for confirming something irreversible
(`DeleteGardenDialog`: cream, `w-[calc(100%-2rem)]`, terracotta confirm
button). `Sheet` for the plant detail panel; `Popover` (`rounded-2xl
bg-cream`) for small inline forms (nickname, follow).

**Inputs:** `Input` is `rounded-full`, `Textarea` `rounded-2xl`, both on
`bg-cream` inside an oat surface. Every field has a `Label` (use `sr-only` when
the design shows none). Field errors are a `<p role="alert" className="text-xs
text-destructive">` (or `text-sm` in dialogs) tied in with `aria-describedby`.

**Toasts:** the single `<Toaster position="top-center" />` lives in
`__root.tsx`; call `toast.success(...)` / `toast.error(...)` from `sonner`.
Never toast a `RateLimitError`: `httpService` has already shown one.

**App components (`components/garden/`):** `GardenCanvas` (the draggable
plan with areas and plant pins), `CanvasThumbnail` (the canvas preview on the
home cards), `PlantAvatar`, `CareRing` (care progress ring, plus
`CARE_ICONS`), `AddPlantDialog`, `CreateRoomDialog` (also exports
`shareUrl` / `copyShare`) and `DeleteGardenDialog`. Put new garden-specific
pieces here and build them from `components/ui`.

## Layout

**Shell (`routes/__root.tsx`):** sets `lang="en"`, the viewport meta, the
default title and description, the stylesheet and fonts, wraps every page in
`QueryClientProvider`, renders `<Outlet />` and the `Toaster`. It also owns the
not-found page and the error page (centred `max-w-md px-4` block, `h1`, muted
text, a primary and an outline action). There is no shared header or nav: each
page draws its own. Per-page titles go in the route's `head()`.

**Pages:** each route renders one `<main className="mx-auto px-4 ...">`.
The side gutter is always `px-4`. Widths: home `max-w-6xl py-8 md:py-14`,
room `max-w-7xl py-5 pb-28` (room for the fixed FAB), single-message pages
(`confirm-follow`, `unsubscribe`) `max-w-md py-14 text-center` with the
content in a `rounded-3xl bg-oat p-8 shadow-soft` card. Grids collapse to one
column on phones (`sm:grid-cols-2 lg:grid-cols-3`, `lg:grid-cols-[1fr_380px]`).

**Headings:** one `h1` per page: `text-4xl md:text-5xl` on home, `text-3xl
md:text-4xl` for the garden name, `text-2xl` on message and empty pages; card
and section titles are `h2` at `text-lg` / `text-2xl`. The small
`Sprout` + "Fernslop" kicker above a heading is `font-display font-bold
text-sage`. Secondary text is `text-muted-foreground`, usually `text-sm`.

## Mobile rules

- Design for a 375 px phone first; no horizontal scrolling at 375 px (or at
  320 px, which `design-check` also tests). Use `min-w-0`, `truncate` and
  `flex-wrap` on rows that can grow.
- Tap targets: at least 24 px always, 44 px wherever the layout allows
  (`DeleteGardenDialog` uses `h-11 sm:h-9` for this). Keep controls apart.
- Dialogs must fit the screen with a margin (`w-[calc(100%-2rem)]` or the
  shadcn default) and scroll inside rather than overflowing.
- Fixed elements (the FAB at `fixed right-5 bottom-5`) need bottom padding on
  the page so they never cover the last control.

## Checking a UI change

Use the `design-check` skill (`.claude/skills/design-check/`): Playwright on
the mock app at 320, 390, 768 and 1280 px, checking overflow, tap targets,
input sizes and off-token colours, with screenshots in `tmp/design-check/`.
