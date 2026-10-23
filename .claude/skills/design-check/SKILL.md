---
name: design-check
description: Look at the running Fernslop frontend in a real browser (Playwright) at mobile, tablet and desktop sizes, take screenshots, and check that the screens are consistent with each other and work on a phone. Use this whenever a designer or QA needs to verify a UI change, review whether pages "fit together" (same fonts, colours, radii, gutters, buttons, headings), check mobile layout (overflow, tap targets, dialogs, small screens), compare design choices across pages, or sign off a UI task - even if the user just says "check the UI", "does it look right on mobile", "review the design" or "take screenshots of the app".
---

# Design check

Checks that the screens of the frontend (`frontend/`) look like one product and hold up on a phone. It has two halves, and you need both:

1. **`scripts/design_audit.py`** drives Chromium through every page at several viewports. It measures things a person eyeballing would miss (a 20px tap target, a 2px sideways scroll, one dialog title in a different weight) and compares pages with each other.
2. **You look at the screenshots.** The script cannot see that a label is hidden behind a pin, that the visual hierarchy is muddled, or that a screen feels like it belongs to a different app. Read the PNGs with the Read tool; this is where most design findings come from.

Used by QA (verdict against an issue's acceptance criteria) and by a designer (what to change so the screens align). Do not fix code as QA. As a designer, propose concrete changes (token, component, class), not just "looks off".

## 1. Know what "aligned" means here

- Read `_docs/design-system.md` first. It describes the React, Tailwind and shadcn frontend: tokens, components and layout rules.
- Tokens and fonts live in `frontend/src/styles.css` (`--moss`, `--oat`, `--font-display`, ...) and the shared components in `frontend/src/components/ui/`. Those are the source of truth; the doc itself says the code wins. Where the doc and the code disagree, say so in your report instead of silently picking one.
- If the task touches a UI, read the issue's acceptance criteria first and check each one visually as well.

## 2. Run the app

Use the in-browser mock so the data is the same every time and no backend is needed:

```sh
cd frontend && VITE_USE_MOCK=true npx vite dev --port 5173   # run in the background
```

Check `curl -s -o /dev/null -w "%{http_code}" http://localhost:5173/` returns 200. To check against the real API, start it with `make backend` (port 8091) and drop `VITE_USE_MOCK`. Stop any server you started when you are done.

## 3. Run the audit

From the repo root. Playwright is run ephemerally with `uv run --with`, so nothing is added to `pyproject.toml` or `package.json` (the project asks before adding dependencies). The version is pinned so it matches the Chromium already in `~/Library/Caches/ms-playwright`; if the script says the browser is missing, tell the user and run the install command it prints (a one-off ~150MB download).

```sh
uv run --with playwright==1.63.0 python .claude/skills/design-check/scripts/design_audit.py \
  --base-url http://localhost:5173 --crawl --out tmp/design-check/<short-name>
```

- `--crawl` also audits the pages linked from `/` (room pages). Dynamic ids differ per browser context in mock mode, so pages are named by link text. Add known paths with `--route /unsubscribe` (repeatable).
- Default viewports: `mobile-small` 320, `mobile` 390, `tablet` 768, `desktop` 1280. Others: `mobile-landscape`, `wide`. Choose with `--viewports mobile,desktop`. Always keep at least one phone size; 320px is where layouts usually break first.
- **States** (dialogs, menus, filled forms, error messages) are where mobile layouts break and the default run never opens them. Describe them in a JSON file and pass `--states file.json`; start from `references/states.example.json` (the create-room dialog). Add a state for every dialog or panel the change touches.
- `--wait-for 'main h1'` if a page needs a specific element before it is measured. `--viewport-only` takes viewport-sized shots instead of full-page ones: use it for fixed elements (full-page shots draw a fixed button in the middle of the page).
- Output: `report.md` (read this), `report.json`, `screenshots/<page>__<viewport>.png`. Exit code 1 means at least one FAIL.

Put output in `tmp/design-check/` (git-ignored). For before/after comparisons run twice with different `--out` names and compare the two reports and screenshots.

## 4. Read the report, then the screenshots

`report.md` has per-page issues, then an "Across pages" section.

| Severity | Meaning | Examples |
|---|---|---|
| FAIL | Broken | sideways scroll, console error, failed request, broken image, tap target under 24px, controls overlapping |
| WARN | Probably a design problem | tap target under 44px, input under 16px (iOS zooms the page), text under 12px, clipped text, missing alt, floating button over a control |
| info | A fact to judge | element styles that differ between pages, colours outside the tokens, fonts, content gutters |

Treat info lines as questions, not verdicts. "h1 is 36px on home and 24px on the not-found page" may be intentional; "dialog title weight 600 where every other h2 is 800" is probably a miss. Decide from the screenshot and the token file, and say which you think it is.

Then open the screenshots with the Read tool: every page at one phone size and at desktop at least, plus every state. Use `references/review-checklist.md` for what to look at; it covers what the script cannot measure.

## 5. Report

Lead with the verdict, then evidence. For QA, use the project format so it can be pasted into the issue:

```
## QA: PASS | FAIL

- [x] <acceptance criterion> - PASS (home @ 390: screenshot path)
- [ ] <acceptance criterion> - FAIL: <what you saw, page, viewport, screenshot path>

Design check: `<command>`, N runs, X fail, Y warn. Report: tmp/design-check/<name>/report.md
```

FAIL only for a criterion that is broken or a script FAIL that is real. WARN and info items go under "Observations" and do not fail a task on their own. For a designer, group findings by cause (one token or component often explains many pages) and list the fix once, with the pages it affects.

If a script finding is a false positive, say so and why rather than dropping it silently; the checks are heuristics.
