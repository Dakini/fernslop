# Visual review checklist

What to look for in the screenshots. The script covers measurable things; these need eyes. Go through each page at a phone size, then desktop, then compare pages side by side.

## Fit together (across pages)

- **Same page chrome.** Header, back link, page title and content gutter sit in the same place on every page. The script reports `<main>` left offsets, but check the title and primary action too.
- **Same vocabulary.** The same kind of thing looks the same everywhere: primary buttons, secondary/ghost buttons, chips and filters, cards, form fields, dialogs, empty and error states. When two pages solve the same problem differently, name both and say which should win.
- **Type scale.** Page titles, section headings and body text step down in a consistent way. Display font (Nunito) for headings, sans (Nunito Sans) for body, per `--font-display` / `--font-sans`.
- **Colour roles.** Brand colour for primary actions, muted tones for secondary things, destructive colour only for destructive actions. Anything off-token in the report: is it a one-off, or a missing token?
- **Shape and depth.** Corner radii, borders and shadows follow one logic (pills for buttons, large radii for cards). A square-cornered or differently shadowed element stands out.
- **Spacing rhythm.** Gaps between sections and between cards are consistent; nothing is cramped against an edge or floating with too much air.
- **Not-found, loading and empty states** use the same layout and tone as the rest of the app.

## Phone (320px and 390px)

- Nothing needs sideways scrolling; text wraps instead of being cut off; long names and long unbroken strings stay inside their container.
- Reading order after stacking makes sense (primary action reachable without scrolling past decoration).
- Touch targets are comfortably tappable and not crowded together; text is readable without zoom.
- Fixed or floating elements (action buttons, sticky bars) do not hide content or controls; check with `--viewport-only`.
- Dialogs and sheets fit the screen, can be scrolled, and their close button is easy to hit. The on-screen keyboard will take roughly half the height, so a form's submit button should still be reachable.
- Content that is dense on desktop (canvas, pins and labels, tables, tab lists) is still legible: labels not overlapping or clipped, horizontal lists wrap or scroll deliberately.
- Landscape (`--viewports mobile-landscape`) for anything fixed to the top or bottom.

## Tablet (768px) and wide

- The layout changes at a sensible breakpoint rather than stretching the phone layout or squeezing the desktop one; no awkward half-empty columns or lines of text that run too wide.

## Quality of the visual result

- Clear hierarchy: one obvious primary action per screen, titles stand out from body text.
- Text contrast is readable on every background, including text over the garden canvas image and on tinted chips.
- Icons and images are crisp and the right size; no broken or stretched images.
