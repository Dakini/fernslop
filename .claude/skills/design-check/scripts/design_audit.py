#!/usr/bin/env python3
"""Screenshot and audit the running frontend at several viewports with Playwright.

Run it ephemerally so no dependency is added to the repo:

    uv run --with playwright python .claude/skills/design-check/scripts/design_audit.py \
        --base-url http://localhost:5173 --crawl --out tmp/design-check/run1

For each route (and optional interaction state) and each viewport it writes a full-page
screenshot and runs DOM checks. It then compares pages with each other (style variants,
colours outside the design tokens, content gutters) because "do the designs fit together"
is a question about the set of pages, not one page. Output: <out>/report.md, report.json
and <out>/screenshots/*.png. Exit code 1 if any check has severity "fail".

Severity: fail = broken (overflow, console error, broken image, tiny or overlapping tap
targets); warn = likely a design problem (tap target under 44px, iOS-zooming input,
tiny text, clipped text); info = a fact for the reviewer to judge (style variants, off-token colours).
"""

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

VIEWPORTS = {
    "mobile-small": dict(width=320, height=640, device_scale_factor=2, is_mobile=True, has_touch=True),
    "mobile": dict(width=390, height=844, device_scale_factor=3, is_mobile=True, has_touch=True),
    "mobile-landscape": dict(width=844, height=390, device_scale_factor=3, is_mobile=True, has_touch=True),
    "tablet": dict(width=768, height=1024, device_scale_factor=2, is_mobile=True, has_touch=True),
    "desktop": dict(width=1280, height=800, device_scale_factor=1, is_mobile=False, has_touch=False),
    "wide": dict(width=1920, height=1080, device_scale_factor=1, is_mobile=False, has_touch=False),
}
DEFAULT_VIEWPORTS = ["mobile-small", "mobile", "tablet", "desktop"]

# Runs inside the page. Returns plain data; Python decides what to do with it.
AUDIT_JS = r"""
(opts) => {
  const vw = window.innerWidth, vh = window.innerHeight;
  const issues = [];
  const add = (severity, check, message, examples) =>
    issues.push({ severity, check, message, examples: (examples || []).slice(0, 6) });

  const describe = (el) => {
    let s = el.tagName.toLowerCase();
    if (el.id) s += '#' + el.id;
    const cls = (typeof el.className === 'string' ? el.className : '').trim().split(/\s+/).filter(Boolean).slice(0, 3);
    if (cls.length) s += '.' + cls.join('.');
    const text = (el.innerText || el.getAttribute('aria-label') || el.getAttribute('alt') || '').trim().replace(/\s+/g, ' ').slice(0, 30);
    return text ? `${s} "${text}"` : s;
  };
  const visible = (el) => {
    const cs = getComputedStyle(el), r = el.getBoundingClientRect();
    if (cs.display === 'none' || cs.visibility === 'hidden' || parseFloat(cs.opacity) === 0) return false;
    if (r.width <= 1 && r.height <= 1) return false; // sr-only and friends
    return r.width > 0 && r.height > 0;
  };
  const clippedByAncestor = (el) => {
    for (let p = el.parentElement; p && p !== document.body; p = p.parentElement) {
      const ox = getComputedStyle(p).overflowX;
      if (ox === 'auto' || ox === 'scroll' || ox === 'hidden' || ox === 'clip') return true;
    }
    return false;
  };
  const all = Array.from(document.body.querySelectorAll('*')).filter(visible);

  // --- Page level -----------------------------------------------------------
  const root = document.documentElement;
  if (root.scrollWidth > vw + 1) {
    const offenders = all.filter((el) => {
      const r = el.getBoundingClientRect();
      return (r.right > vw + 1 || r.left < -1) && getComputedStyle(el).position !== 'fixed' && !clippedByAncestor(el);
    }).filter((el) => !all.some((o) => o !== el && o.contains(el) && o.getBoundingClientRect().right > vw + 1 && !clippedByAncestor(o)))
      .map((el) => `${describe(el)} right=${Math.round(el.getBoundingClientRect().right)}`);
    add('fail', 'horizontal-overflow', `Page is ${root.scrollWidth}px wide in a ${vw}px viewport (sideways scrolling).`, offenders);
  }
  if (opts.mobile && !document.querySelector('meta[name=viewport]')) {
    add('fail', 'viewport-meta', 'No <meta name="viewport">; mobile browsers will render a desktop-width page.', []);
  }

  // --- Interactive elements -------------------------------------------------
  const interactiveSel = 'a[href], button, input:not([type=hidden]), select, textarea, [role=button], [role=link], [role=tab], [role=menuitem], [tabindex]:not([tabindex="-1"])';
  const interactive = all.filter((el) => el.matches(interactiveSel) && !el.disabled);
  if (opts.touch) {
    const tiny = [], small = [];
    for (const el of interactive) {
      if (el.tagName === 'A' && getComputedStyle(el).display === 'inline') continue; // inline text link: exempt (WCAG 2.5.8)
      let r = el.getBoundingClientRect();
      if (el.matches('input[type=checkbox],input[type=radio]') && el.closest('label')) r = el.closest('label').getBoundingClientRect();
      const m = Math.min(r.width, r.height);
      const label = `${describe(el)} ${Math.round(r.width)}x${Math.round(r.height)}`;
      if (m < 24) tiny.push(label); else if (m < 44) small.push(label);
    }
    if (tiny.length) add('fail', 'tap-target-tiny', `${tiny.length} tap target(s) under 24px (WCAG 2.5.8 minimum).`, tiny);
    if (small.length) add('warn', 'tap-target-small', `${small.length} tap target(s) under 44px (recommended touch size).`, small);
  }
  const overlaps = [];
  const cand = interactive.slice(0, 300);
  for (let i = 0; i < cand.length; i++) for (let j = i + 1; j < cand.length; j++) {
    const a = cand[i], b = cand[j];
    if (a.contains(b) || b.contains(a)) continue;
    const ra = a.getBoundingClientRect(), rb = b.getBoundingClientRect();
    const w = Math.min(ra.right, rb.right) - Math.max(ra.left, rb.left);
    const h = Math.min(ra.bottom, rb.bottom) - Math.max(ra.top, rb.top);
    if (w > 0 && h > 0 && (w * h) / Math.min(ra.width * ra.height, rb.width * rb.height) > 0.3)
      overlaps.push(`${describe(a)} overlaps ${describe(b)}`);
  }
  if (overlaps.length) add('fail', 'interactive-overlap', `${overlaps.length} pair(s) of controls overlap, so one is hard to tap.`, overlaps);

  if (opts.mobile) {
    const zoom = interactive.filter((el) => el.matches('input:not([type=checkbox]):not([type=radio]):not([type=range]),select,textarea') && parseFloat(getComputedStyle(el).fontSize) < 16)
      .map((el) => `${describe(el)} ${getComputedStyle(el).fontSize}`);
    if (zoom.length) add('warn', 'input-font-size', 'Form fields under 16px make iOS Safari zoom the page on focus.', zoom);
  }

  // --- Text and images ------------------------------------------------------
  const smallText = all.filter((el) => Array.from(el.childNodes).some((n) => n.nodeType === 3 && n.textContent.trim()) && parseFloat(getComputedStyle(el).fontSize) < 12)
    .map((el) => `${describe(el)} ${getComputedStyle(el).fontSize}`);
  if (smallText.length) add('warn', 'text-too-small', `${smallText.length} text element(s) under 12px.`, smallText);

  const clipped = all.filter((el) => {
    const cs = getComputedStyle(el);
    return cs.overflowX === 'hidden' && cs.textOverflow !== 'ellipsis' && el.scrollWidth > el.clientWidth + 1 && (el.innerText || '').trim();
  }).map((el) => `${describe(el)} content ${el.scrollWidth}px in ${el.clientWidth}px`);
  if (clipped.length) add('warn', 'text-clipped', `${clipped.length} element(s) hide overflowing content without an ellipsis.`, clipped);

  const imgs = Array.from(document.images).filter((i) => i.complete !== undefined);
  const broken = imgs.filter((i) => i.complete && i.naturalWidth === 0 && i.getAttribute('src')).map((i) => i.getAttribute('src').slice(0, 80));
  if (broken.length) add('fail', 'broken-image', `${broken.length} image(s) failed to load.`, broken);
  const noAlt = imgs.filter((i) => visible(i) && !i.hasAttribute('alt') && i.getAttribute('role') !== 'presentation').map(describe);
  if (noAlt.length) add('warn', 'image-alt', `${noAlt.length} image(s) have no alt attribute.`, noAlt);

  if (opts.mobile) {
    const bars = all.filter((el) => ['fixed', 'sticky'].includes(getComputedStyle(el).position)).filter((el) => {
      const r = el.getBoundingClientRect();
      const overlay = r.width >= vw - 1 && r.height >= vh - 1; // dialog backdrop, intentional
      return !overlay && r.height > vh * 0.3 && r.width > vw * 0.8;
    }).map(describe);
    if (bars.length) add('warn', 'fixed-covers-screen', 'Fixed/sticky element covers over 30% of the screen height.', bars);
  }

  // --- Facts for cross-page comparison --------------------------------------
  const cv = document.createElement('canvas'); cv.width = cv.height = 1;
  const cx = cv.getContext('2d', { willReadFrequently: true });
  const rgba = (c) => { cx.clearRect(0, 0, 1, 1); cx.fillStyle = '#000'; cx.fillStyle = c; cx.fillRect(0, 0, 1, 1); return Array.from(cx.getImageData(0, 0, 1, 1).data); };

  const probe = document.createElement('span'); document.body.appendChild(probe);
  const tokens = {}; const fontTokens = {};
  const names = new Set();
  const walk = (rules) => { for (const rule of rules) {
    if (rule.style) for (const n of rule.style) if (n.startsWith('--')) names.add(n);
    if (rule.cssRules) walk(rule.cssRules);
  } };
  for (const sheet of document.styleSheets) { try { walk(sheet.cssRules); } catch (e) { /* cross-origin sheet */ } }
  for (const n of names) {
    probe.style.color = 'rgb(1, 2, 3)'; probe.style.color = `var(${n})`;
    const resolved = getComputedStyle(probe).color;
    const v = getComputedStyle(document.documentElement).getPropertyValue(n).trim();
    if (n.startsWith('--font-')) { fontTokens[n] = v; continue; }
    if (!v || resolved === 'rgb(1, 2, 3)' || /^[\d.]/.test(v) || /(px|rem|em|%)\s*$/.test(v) && !/(color|oklch|rgb|hsl)/.test(v)) continue;
    const c = rgba(resolved); if (c[3] === 255) tokens[n] = c.slice(0, 3);
  }
  probe.remove();

  const groups = {
    h1: 'h1', h2: 'h2', h3: 'h3', button: 'button, [role=button]', link: 'a[href]',
    field: 'input:not([type=checkbox]):not([type=radio]):not([type=hidden]), select, textarea',
  };
  const styles = [];
  for (const [cat, sel] of Object.entries(groups)) {
    for (const el of all.filter((e) => e.matches(sel)).slice(0, 60)) {
      const cs = getComputedStyle(el);
      const bg = rgba(cs.backgroundColor), fg = rgba(cs.color);
      styles.push({
        cat, el: describe(el),
        props: {
          'font-family': cs.fontFamily.split(',')[0].replace(/["']/g, '').trim(),
          'font-size': cs.fontSize, 'font-weight': cs.fontWeight,
          'color': fg[3] === 255 ? `rgb(${fg.slice(0, 3)})` : 'translucent',
          'background': bg[3] === 0 ? 'none' : bg[3] === 255 ? `rgb(${bg.slice(0, 3)})` : 'translucent',
          'border-radius': cs.borderTopLeftRadius,
          'padding': `${cs.paddingTop} ${cs.paddingRight} ${cs.paddingBottom} ${cs.paddingLeft}`,
        },
      });
    }
  }

  const colors = {}; const fonts = {};
  for (const el of all.slice(0, 1500)) {
    const cs = getComputedStyle(el);
    const fam = cs.fontFamily.split(',')[0].replace(/["']/g, '').trim();
    if ((el.childNodes.length && Array.from(el.childNodes).some((n) => n.nodeType === 3 && n.textContent.trim()))) fonts[fam] = (fonts[fam] || 0) + 1;
    const used = [['text', cs.color, true], ['background', cs.backgroundColor, true], ['border', cs.borderTopColor, parseFloat(cs.borderTopWidth) > 0]];
    for (const [kind, value, relevant] of used) {
      if (!relevant) continue;
      const c = rgba(value); if (c[3] < 255) continue; // translucent mixes are not compared with tokens
      const key = c.slice(0, 3).join(',');
      (colors[key] = colors[key] || { count: 0, kinds: {}, example: describe(el) }).count++;
      colors[key].kinds[kind] = (colors[key].kinds[kind] || 0) + 1;
    }
  }

  const rect = (el) => { if (!el) return null; const r = el.getBoundingClientRect(); return { left: Math.round(r.left), right: Math.round(vw - r.right), width: Math.round(r.width) }; };
  const layout = { main: rect(document.querySelector('main')), h1: rect(document.querySelector('h1')) };

  return { issues, styles, colors, fonts, tokens, fontTokens, layout, title: document.title, scrollHeight: root.scrollHeight };
}
"""


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "home"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--base-url", default="http://localhost:5173")
    p.add_argument("--route", action="append", default=[], help="Path to audit, repeatable (default: /)")
    p.add_argument("--crawl", action="store_true", help="Also audit same-origin links found on the first route")
    p.add_argument("--max-crawl", type=int, default=6, help="Max routes added by --crawl")
    p.add_argument("--viewports", default=",".join(DEFAULT_VIEWPORTS), help=f"Comma list from: {', '.join(VIEWPORTS)}")
    p.add_argument("--states", help="JSON file: [{name, route, steps:[{click|fill|press|wait_for}]}] for dialogs, menus, filled forms")
    p.add_argument("--wait-for", help="CSS selector that must be visible before auditing a page (e.g. 'main h1')")
    p.add_argument("--settle-ms", type=int, default=800, help="Extra wait after load (animations, data fetching)")
    p.add_argument("--viewport-only", action="store_true", help="Screenshot the visible viewport instead of the full page")
    p.add_argument("--out", default="tmp/design-check/latest")
    return p.parse_args()


def run_steps(page, steps):
    for step in steps:
        if "click" in step:
            page.locator(step["click"]).first.click()
        elif "fill" in step:
            selector, value = step["fill"]
            page.locator(selector).first.fill(value)
        elif "press" in step:
            page.keyboard.press(step["press"])
        elif "wait_for" in step:
            page.locator(step["wait_for"]).first.wait_for(state="visible")
        page.wait_for_timeout(step.get("wait_ms", 300))


def audit_page(ctx, base_url, target, vp_name, vp, args, shots):
    page = ctx.new_page()
    console, failed = [], []
    page.on("console", lambda m: console.append(f"{m.type}: {m.text[:200]}") if m.type == "error" else None)
    page.on("pageerror", lambda e: console.append(f"pageerror: {str(e)[:200]}"))
    origin = urlparse(base_url).netloc
    page.on("response", lambda r: failed.append(f"{r.status} {r.url[:120]}") if r.status >= 400 and urlparse(r.url).netloc == origin else None)
    # "load", not "networkidle": the room page keeps an SSE stream open, so the network is never idle.
    page.goto(urljoin(base_url, target["route"]), wait_until="load")
    if args.wait_for:
        page.locator(args.wait_for).first.wait_for(state="visible", timeout=10000)
    page.wait_for_timeout(args.settle_ms)
    run_steps(page, target.get("steps", []))
    name = f"{slug(target['name'])}__{vp_name}"
    shot = shots / f"{name}.png"
    page.screenshot(path=str(shot), full_page=not args.viewport_only, animations="disabled")
    data = page.evaluate(AUDIT_JS, {"mobile": vp["is_mobile"], "touch": vp["has_touch"]})
    page.close()
    for message in console:
        data["issues"].append({"severity": "fail", "check": "console-error", "message": message, "examples": []})
    for message in failed:
        data["issues"].append({"severity": "fail", "check": "failed-request", "message": message, "examples": []})
    return {"target": target["name"], "route": target["route"], "viewport": vp_name, "screenshot": str(shot), **data}


def crawl(ctx, base_url, route, limit):
    page = ctx.new_page()
    page.goto(urljoin(base_url, route), wait_until="load")
    page.wait_for_timeout(1000)
    hrefs = page.eval_on_selector_all("a[href]", "els => els.map(e => e.getAttribute('href'))")
    page.close()
    found = []
    for href in hrefs:
        parsed = urlparse(urljoin(base_url, href))
        path = parsed.path + (f"?{parsed.query}" if parsed.query else "")
        if parsed.netloc != urlparse(base_url).netloc or parsed.path.startswith("/api") or href.startswith("#"):
            continue
        if path != route and path not in found:
            found.append(path)
    return found[:limit]


def pct(n, total):
    return f"{round(100 * n / total)}%" if total else "0%"


def cross_page(results):
    """Facts that only make sense across pages. Everything here is severity info."""
    notes = []
    by_vp = defaultdict(list)
    for r in results:
        by_vp[r["viewport"]].append(r)

    # Style variants per element category and property, per viewport (responsive sizes are expected to differ).
    for vp, runs in by_vp.items():
        seen = defaultdict(lambda: defaultdict(Counter))
        example = {}
        for r in runs:
            for s in r["styles"]:
                for prop, value in s["props"].items():
                    seen[s["cat"]][prop][value] += 1
                    example.setdefault((s["cat"], prop, value), f"{r['target']}: {s['el']}")
        for cat, props in seen.items():
            for prop, counter in props.items():
                if len(counter) < 2:
                    continue
                total = sum(counter.values())
                top = counter.most_common(4)
                minority = [v for v, _ in top[1:]]
                if prop in ("padding", "font-size", "background", "color") and len(counter) > 4:
                    continue  # too varied to be an outlier signal, visual review covers it
                lines = ", ".join(f"`{v}` x{c}" for v, c in top)
                outliers = "; ".join(f"`{v}` e.g. {example[(cat, prop, v)]}" for v in minority[:2])
                notes.append(f"[{vp}] {cat} {prop}: {lines} ({total} elements). Minority: {outliers}")

    # Colours not in the design tokens, per page (desktop-sized run if present).
    token_rgb = {}
    for r in results:
        for name, rgb in r["tokens"].items():
            token_rgb.setdefault(tuple(rgb), []).append(name)
    off = {}
    for r in results:
        for key, info in r["colors"].items():
            rgb = tuple(int(x) for x in key.split(","))
            if any(all(abs(a - b) <= 4 for a, b in zip(rgb, t)) for t in token_rgb):
                continue
            if rgb in ((255, 255, 255), (0, 0, 0)):
                continue
            entry = off.setdefault(rgb, {"count": 0, "pages": set(), "example": info["example"], "kinds": Counter()})
            entry["count"] += info["count"]
            entry["pages"].add(r["target"])
            entry["kinds"].update(info["kinds"])
    token_notes = [
        f"rgb{rgb} used {e['count']}x ({', '.join(f'{k} {v}' for k, v in e['kinds'].items())}) on {', '.join(sorted(e['pages']))}; e.g. {e['example']}"
        for rgb, e in sorted(off.items(), key=lambda kv: -kv[1]["count"])[:12]
    ]

    # Fonts outside the font tokens.
    font_tokens = set()
    for r in results:
        for v in r["fontTokens"].values():
            font_tokens.update(f.strip().strip("\"'") for f in v.split(",")[:1])
    fonts = Counter()
    for r in results:
        fonts.update(r["fonts"])
    font_notes = [f"{family} x{count}" + ("" if family in font_tokens else "  <- not a --font-* token") for family, count in fonts.most_common(6)]

    # Content gutters: the same page chrome should sit at the same left/right offset on every route.
    gutter_notes = []
    for vp, runs in by_vp.items():
        rows = [(r["target"], r["layout"]["main"]) for r in runs if r["layout"]["main"]]
        lefts = {m["left"] for _, m in rows}
        if len(rows) > 1 and (max(lefts) - min(lefts) > 2):
            gutter_notes.append(f"[{vp}] <main> left offset differs: " + ", ".join(f"{t}={m['left']}px" for t, m in rows))
    return notes, token_notes, font_notes, gutter_notes


def write_report(out, args, results, extras):
    notes, token_notes, font_notes, gutter_notes = extras
    counts = lambda r, sev: sum(1 for i in r["issues"] if i["severity"] == sev)
    lines = [f"# Design check {datetime.now():%Y-%m-%d %H:%M}", "", f"Base URL: {args.base_url}", ""]
    lines += ["## Summary", "", "| Page | Viewport | Fail | Warn | Screenshot |", "|---|---|---|---|---|"]
    for r in results:
        lines.append(f"| {r['target']} | {r['viewport']} | {counts(r, 'fail')} | {counts(r, 'warn')} | {r['screenshot']} |")
    lines += ["", "## Issues", ""]
    any_issue = False
    for r in results:
        issues = [i for i in r["issues"]]
        if not issues:
            continue
        any_issue = True
        lines.append(f"### {r['target']} @ {r['viewport']}")
        for i in sorted(issues, key=lambda i: {"fail": 0, "warn": 1}.get(i["severity"], 2)):
            lines.append(f"- **{i['severity'].upper()}** `{i['check']}`: {i['message']}")
            lines += [f"  - {e}" for e in i["examples"]]
        lines.append("")
    if not any_issue:
        lines += ["No automated issues.", ""]
    lines += ["## Across pages (info: judge these against the screenshots)", ""]
    lines += ["### Style variants", ""] + ([f"- {n}" for n in notes] or ["- None: buttons, headings, links and fields are uniform."]) + [""]
    lines += ["### Colours outside the design tokens", ""] + ([f"- {n}" for n in token_notes] or ["- None."]) + [""]
    lines += ["### Fonts", ""] + [f"- {n}" for n in font_notes] + [""]
    lines += ["### Content gutters", ""] + ([f"- {n}" for n in gutter_notes] or ["- `<main>` sits at the same left offset on every page."]) + [""]
    (out / "report.md").write_text("\n".join(lines))
    (out / "report.json").write_text(json.dumps({"results": results, "cross_page": {"style_variants": notes, "off_token_colors": token_notes, "fonts": font_notes, "gutters": gutter_notes}}, indent=2))


def main() -> int:
    args = parse_args()
    out = Path(args.out)
    shots = out / "screenshots"
    shots.mkdir(parents=True, exist_ok=True)
    viewports = [v.strip() for v in args.viewports.split(",") if v.strip()]
    unknown = [v for v in viewports if v not in VIEWPORTS]
    if unknown:
        sys.exit(f"Unknown viewport(s): {', '.join(unknown)}. Choose from: {', '.join(VIEWPORTS)}")
    routes = args.route or ["/"]
    results = []
    with sync_playwright() as pw:
        try:
            browser = pw.chromium.launch()
        except PlaywrightError as error:
            sys.exit(f"{error}\n\nIf the browser is missing, install it once with:\n  uv run --with playwright playwright install chromium")
        targets = []
        for vp_name in viewports:
            vp = VIEWPORTS[vp_name]
            ctx = browser.new_context(
                viewport={"width": vp["width"], "height": vp["height"]}, device_scale_factor=vp["device_scale_factor"],
                is_mobile=vp["is_mobile"], has_touch=vp["has_touch"], reduced_motion="reduce",
            )
            if not targets:  # resolved once, with the first viewport's context
                targets = [{"name": "home" if r == "/" else r, "route": r} for r in routes]
                if args.crawl:
                    extra = crawl(ctx, args.base_url, routes[0], args.max_crawl)
                    targets += [{"name": p, "route": p} for p in extra if p not in routes]
                if args.states:
                    for state in json.loads(Path(args.states).read_text()):
                        targets.append({"name": state["name"], "route": state.get("route", "/"), "steps": state.get("steps", [])})
                print(f"Auditing {len(targets)} page(s) x {len(viewports)} viewport(s): " + ", ".join(t["name"] for t in targets))
            for target in targets:
                try:
                    results.append(audit_page(ctx, args.base_url, target, vp_name, vp, args, shots))
                except PlaywrightError as error:
                    sys.exit(f"Could not audit {target['route']} at {vp_name}: {str(error).splitlines()[0]}\nIs the frontend running at {args.base_url}?")
            ctx.close()
        browser.close()
    write_report(out, args, results, cross_page(results))
    fails = sum(1 for r in results for i in r["issues"] if i["severity"] == "fail")
    warns = sum(1 for r in results for i in r["issues"] if i["severity"] == "warn")
    print(f"{len(results)} runs, {fails} fail, {warns} warn. Report: {out / 'report.md'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
