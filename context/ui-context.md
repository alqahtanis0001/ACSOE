# UI Context

## What this interface is

An instrument panel for one operator watching a system that refuses almost everything.

That framing drives every decision below. Most trading interfaces are built around activity — flashing tickers, order tickets, green candles. This one's honest default state is **nothing qualified today**. A console that looks empty most of the time is not broken; it is telling the truth. The design's job is to make stillness legible and informative rather than make it look like a failure.

The primary question the screen must answer in under two seconds: *is this safe, and what is it doing?*
The secondary question: *why was that rejected?*

## The one bold move

**Live mode changes the entire frame of the page.** A 3px amber border around the whole viewport, plus the mode word in the status band. Paper mode has no border at all.

Amber (`--live`) is reserved. It appears nowhere else in the interface — not for warnings, not for charts, not for hover states. It means one thing: real money is at risk right now. That reservation is what makes it work. Everything else in the design stays quiet so this reads instantly.

## Palette

A cool slate ground, not black. Deliberately warmer and less absolute than the usual near-black trading theme, because this screen is stared at for hours and pure black plus neon is fatiguing.

| Role | Token | Hex |
|---|---|---|
| Ground | `--ground` | `#12161A` |
| Surface | `--surface` | `#1A2027` |
| Raised | `--raised` | `#232B33` |
| Hairline | `--line` | `#2E3840` |
| Text primary | `--text` | `#E4E9ED` |
| Text secondary | `--text-2` | `#9AA7B2` |
| Text muted | `--text-3` | `#66757F` |
| Positive | `--pos` | `#4E9A6B` |
| Negative | `--neg` | `#C2604F` |
| Live (reserved) | `--live` | `#D9A441` |
| Interactive | `--accent` | `#5B8FB9` |

Positive and negative are deliberately muted. This system's outcomes are fractions of a percent. Bright green and red would overstate them and make a 0.3% gain look like a jackpot.

Never use a raw hex in a component. Tokens only, declared once on `:root`.

## Typography

**IBM Plex Sans** for interface text. **IBM Plex Mono** for every number.

Chosen because Plex was designed for technical instrumentation and the two faces are a designed pair rather than an arbitrary combination, and because Plex Mono has genuinely good tabular figures — which this interface depends on more than anything else.

| Role | Face | Size | Weight |
|---|---|---|---|
| Status band figure | Plex Mono | 32px | 500 |
| Section heading | Plex Sans | 16px | 500 |
| Body and labels | Plex Sans | 14px | 400 |
| Table numbers | Plex Mono | 13px | 400 |
| Secondary detail | Plex Sans | 13px | 400 |

Sentence case everywhere. No all-caps labels, no tracked-out eyebrows above headings.

## Number rules

These are not stylistic. Misread numbers cost money.

1. `font-variant-numeric: tabular-nums` on every numeric element, without exception. Columns of prices must align digit-for-digit or they cannot be scanned.
2. Percentages are always explicitly signed: `+0.62%`, `−1.50%`. Never bare.
3. **Colour is never the only signal.** The sign carries the meaning; colour reinforces it. A red-green colourblind operator must lose nothing.
4. Money renders to the quote currency's own precision from `AssetPairs`, never more digits than the exchange itself uses.
5. Any figure older than `console.stale_after_ms` renders at 50% opacity with its age shown beside it. Stale data must look stale.
6. Use a proper minus sign (−, U+2212) in numeric output, not a hyphen. Hyphens break tabular alignment.

## Layout

Not a grid of cards. Cards-of-uniform-radius is the default that makes every dashboard look like every other dashboard.

```
┌──────────────────────────────────────────────────┐
│  STATUS BAND — fixed, never scrolls              │
│  Balance    Mode    State    Data age    [ ⏻ ]   │
├──────────────────────────────────────────────────┤
│  OPEN POSITIONS — only rendered if any exist     │
├──────────────────────────────────────────────────┤
│                                                  │
│  CYCLE FEED — single column, newest first        │
│  each row: time · pair · outcome · reason        │
│                                                  │
└──────────────────────────────────────────────────┘
```

The status band is the hero and is always visible. Everything below it scrolls. Content is left-aligned; numbers are right-aligned within their column.

Radius is used to encode depth, not decoration: `4px` on inline elements, `8px` on panels, `0` on table rows. No shadows anywhere — separation comes from the hairline and the surface step.

## The empty state is the main state

When nothing qualified, do not show "No results." Show what the system actually did:

> Scanned 412 pairs. 38 entered the tradable universe. 3 reached the cost gate. None cleared it.

Stillness becomes information. This is the single most-viewed screen state in the product and deserves more design attention than the rare active trade, not less.

## Restart is visible

A daemon always starts `idle` and never restores its mode, so a crash at 3am leaves a system that is up, watching its open positions, and not trading. That is the safe behaviour, but it is silent: the status band would read `Idle`, which is also what it reads before the operator has ever pressed Activate.

When the daemon's `run_id` has changed since the console last saw one and the mode is `idle`, the State field reads `Idle — restarted, not trading`, and it keeps reading that until the operator activates or freezes. Text only, no colour: amber is reserved for live mode, and the sign has to carry the meaning anyway.

The two states are not the same event and must not look the same. One is a system waiting to be started; the other is a system that stopped on its own.

## Motion

Effectively none. No entrance animations, no hover lifts, no fades on scroll.

The only permitted motion is a 200ms background flash on a value that has just changed, so a change is noticed without the eye being dragged around. Respect `prefers-reduced-motion` by dropping even that.

Continuously animating numbers hide real changes among fake ones.

## Copy

- Buttons say what happens: `Activate`, `Freeze`, `Close all positions`. Never `Submit`.
- An action keeps its name through the whole flow. `Freeze` produces the state `Frozen`.
- Rejection reasons are written for the operator, not the log: "Net edge −0.21% after fees" beats `cost_gate_fail`.
- Errors state what happened and what to do. They never apologise and are never vague.

## Stack

FastAPI serving one HTML page, vanilla JavaScript, a WebSocket for live updates. No build step, no framework, no npm.

The page is read-only except for three commands — Activate, Freeze, Close all — which write rows to the SQLite command table. **The console holds no credentials and can never place an order.**

## How the console learns about changes

The daemon and the console are separate processes sharing SQLite. The console polls a monotonically increasing `updated_at` watermark at `console.poll_interval_ms` from config — never a hardcoded number — and pushes over the WebSocket only when the watermark moves.

`console.poll_interval_ms` defaults to 500 and **must always be well below `console.stale_after_ms`** (default 120000, two loop ticks). Config validation rejects a poll interval above a quarter of the stale threshold. Without that rule a slow poll would fade the entire screen to half opacity permanently. No triggers, no file watching, no polling from the browser.

The port is `console.port` in config. The README's `127.0.0.1:8765` is the default value, not a second source of truth.

## Screens not yet designed

`ui-context.md` specifies the status band, open positions and the cycle feed. History, research, the leaderboard and the SHAP view are named in the phase criteria but have no design here.

Until they do, they inherit every rule above — palette, type, number rules, the empty state principle — and use the same table treatment as the cycle feed: left-aligned labels, right-aligned tabular numbers, hairline separators, no cards. If a screen needs a treatment these rules do not cover, that is an open question for the operator, not a decision for the agent building it.

## Quality floor

Not optional, and not to be announced in the UI: visible keyboard focus rings, `prefers-reduced-motion` respected, all text meeting WCAG AA against its own background, and the layout usable down to a 1024px window. It does not need to work on a phone.
