# 18 — Design tokens, stylesheet and the page shell

**Owner:** C — Interface and models

## Goal

The single HTML page and the token block every screen draws from, including the live-mode amber
frame and the quality floor — so no later spec has to invent a colour, a size or a focus ring.

## Implementation

1. Create `src/acsoe/console/templates/index.html` — **one page, the only page**, per
   `ui-context.md`. It carries the fixed status band, the open-positions region, the cycle feed,
   and the history and research panes as sibling sections switched client-side.
2. Create `src/acsoe/console/static/tokens.css` — the `:root` block declaring every token from
   the `ui-context.md` palette table exactly once: `--ground`, `--surface`, `--raised`,
   `--line`, `--text`, `--text-2`, `--text-3`, `--pos`, `--neg`, `--live`, `--accent`.
   **This file is the only place in the console where a raw hex may appear.**
3. Create `src/acsoe/console/static/console.css` — layout and type. IBM Plex Sans for interface
   text, IBM Plex Mono for every number, self-hosted under
   `src/acsoe/console/static/fonts/` with local `@font-face` rules. No CDN: the console must
   render with no network. Type scale exactly as the `ui-context.md` table sets it. Sentence
   case throughout, no all-caps labels, no tracked-out eyebrows.
4. Radius encodes depth, not decoration: `4px` inline, `8px` on panels, `0` on table rows. No
   shadows anywhere — separation comes from the hairline and the surface step.
5. **The one bold move.** A 3px `--live` border around the whole viewport when the mode is live,
   and **no border at all** in paper. Amber appears nowhere else in the interface.
6. Layout: the status band is fixed and never scrolls; everything below it scrolls. Content
   left-aligned, numbers right-aligned within their column.
7. A `.num` class carrying `font-variant-numeric: tabular-nums`, which every numeric cell in
   every later spec applies without exception.
8. Quality floor, not announced in the UI: a visible `:focus-visible` ring on every interactive
   element, a `@media (prefers-reduced-motion: reduce)` block that drops even the 200ms change
   flash, all text meeting WCAG AA against its own background, and a layout usable down to a
   1024px window.

## Scope Limits

- Do **not** bind data, render screen content, open a WebSocket, or wire a command. Structure
  and style only — specs 19 to 24 fill it.
- **Never a raw hex outside `tokens.css`.** Not in `console.css`, not in the template, not in
  JavaScript.
- **Never use `--live` for anything but live mode** — not a warning, not a chart, not a hover
  state. The reservation is what makes it read instantly.
- Do **not** add a CDN link, an npm dependency, a build step or a CSS framework.
- Do **not** add entrance animations, hover lifts, or fades on scroll. The 200ms flash on a
  changed value is the only motion permitted anywhere.
- Do **not** use colour as the only signal for anything.
- Do **not** design the history, leaderboard or SHAP screens beyond the inherited table
  treatment — specs 21 and 22 carry that, and a treatment those rules do not cover is an
  operator question, not an agent decision.

## Check When Done

- The page loads with the server offline from any third party: zero external requests.
- A live-mode config renders the amber frame; a paper config renders no border — one test each.
- A scan of `src/acsoe/console/` finds no hex literal outside `tokens.css`.
- Tabbing reaches every control with a visible ring, and `prefers-reduced-motion: reduce` drops
  the flash.
- The layout is usable at 1024px with no horizontal scroll.
- `pytest tests/ -q` · `mypy --strict src/` · `ruff check src/` · `python scripts/verify.py --phase 1`
