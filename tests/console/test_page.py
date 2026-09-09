"""The page shell, the tokens and the stylesheet. Spec 18.

The one bold move gets most of the attention: **live mode changes the entire
frame of the page, and paper has no border at all.** Amber is reserved — it
appears nowhere else in the interface, and that reservation is the only reason it
reads instantly. So it is asserted from both ends, in both modes, and a border
declared anywhere else on the frame is a failure rather than a style opinion.

Everything else here is the quality floor of `ui-context.md`: no external
request, a visible focus ring, reduced motion honoured, and a layout usable at
1024px. None of it is announced in the UI and all of it is checkable without a
browser.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from acsoe.console.app import (
    MODE_PLACEHOLDER,
    STATIC_DIR,
    TEMPLATE_PATH,
    create_app,
    render_page,
)

TOKENS_CSS = STATIC_DIR / "tokens.css"
CONSOLE_CSS = STATIC_DIR / "console.css"
FONTS_DIR = STATIC_DIR / "fonts"

#: The eleven tokens of the `ui-context.md` palette table. Named here rather than
#: read out of `tokens.css`, so this is an independent statement of the same fact
#: — a test that read the file it is checking would pass whatever the file said.
PALETTE_TOKENS = (
    "--ground",
    "--surface",
    "--raised",
    "--line",
    "--text",
    "--text-2",
    "--text-3",
    "--pos",
    "--neg",
    "--live",
    "--accent",
)

#: The five type roles of the `ui-context.md` table.
TYPE_SIZES = {
    "--size-figure": "32px",
    "--size-heading": "16px",
    "--size-body": "14px",
    "--size-number": "13px",
    "--size-detail": "13px",
}


def stylesheets() -> dict[Path, str]:
    return {path: path.read_text(encoding="utf-8") for path in sorted(STATIC_DIR.rglob("*.css"))}


class _StubConfig:
    def __init__(self, mode: str) -> None:
        self._mode = mode

    @property
    def mode(self) -> Any:
        return self._mode

    def get(self, dotted_key: str, /) -> Any:
        assert dotted_key == "console.stale_after_ms"
        return 120_000


# --------------------------------------------------------------------------- #
# The one bold move
# --------------------------------------------------------------------------- #


def test_a_live_page_carries_the_live_mode_attribute() -> None:
    """The 3px amber frame is keyed off this attribute and off nothing else."""
    assert 'data-mode="live"' in _visible(render_page("live"))


def test_a_paper_page_carries_no_live_marker_anywhere() -> None:
    """Paper mode has no border at all, so it must not claim live in any form."""
    paper = _visible(render_page("paper"))
    assert 'data-mode="paper"' in paper
    assert 'data-mode="live"' not in paper


def test_a_replay_page_is_not_amber_either() -> None:
    """Amber means real money is at risk right now. Replay is offline."""
    replay = _visible(render_page("replay"))
    assert 'data-mode="replay"' in replay
    assert 'data-mode="live"' not in replay


def test_the_live_frame_is_the_only_border_on_the_page_frame() -> None:
    """A second frame border, or one not keyed to live, would put amber on paper.

    Asserted across every stylesheet rather than only the one that declares it,
    because the failure this catches is a rule added somewhere else later.
    """
    offenders: list[str] = []
    live_rules: list[str] = []
    for path, text in stylesheets().items():
        for selector, block in _rules(text):
            if not _touches_the_frame(selector):
                continue
            for name, value in _declarations(block):
                if name != "border" or value.lower() in ("none", "0", "0px"):
                    continue
                if 'data-mode="live"' in selector:
                    live_rules.append(f"{path.name}: {selector}")
                else:
                    offenders.append(f"{path.name}: {selector} {{ {name}: {value} }}")
    assert offenders == [], offenders
    assert len(live_rules) == 1, live_rules


def test_amber_is_used_for_nothing_but_live_mode() -> None:
    """Not for a warning, not for a chart, not for a hover state.

    The reservation is what makes it read instantly, and it is the single easiest
    thing in this interface to erode by accident.
    """
    allowed = ('html[data-mode="live"]', ".band__mode--live")
    for path, text in stylesheets().items():
        for selector, block in _rules(text):
            if selector.strip() == ":root":
                continue
            if "var(--live)" not in block:
                continue
            assert selector.strip() in allowed, f"{path.name}: {selector} uses var(--live)"


# --------------------------------------------------------------------------- #
# Zero external requests
# --------------------------------------------------------------------------- #


def test_the_page_fetches_nothing_from_a_third_party() -> None:
    """No CDN, no npm, no build step: the page must render with no network.

    Scanned as absolute and protocol-relative URLs in the markup and in every
    stylesheet, because a `@import url(https://fonts.googleapis.com/...)` is the
    exact shape this forbids and it does not look like a `<link>` tag.
    """
    external = re.compile(r"""(?:https?:)?//[a-z0-9.-]+""", re.I)
    sources = {TEMPLATE_PATH: TEMPLATE_PATH.read_text(encoding="utf-8"), **stylesheets()}
    offences: list[str] = []
    for path, text in sources.items():
        body = _strip_comments(path, text)
        offences.extend(f"{path.name}: {hit}" for hit in external.findall(body))
    assert offences == [], offences


def test_every_font_the_stylesheet_names_is_present_in_the_package() -> None:
    """Self-hosted, under `static/fonts/`.

    A `@font-face` pointing at a file that is not there fails silently: the
    browser falls back, the numbers stop being tabular, and nothing in the console
    says so.
    """
    css = CONSOLE_CSS.read_text(encoding="utf-8")
    referenced = set(re.findall(r"""url\(["']?([^"')]+)["']?\)""", css))
    assert referenced, "console.css declares no @font-face src"
    for reference in sorted(referenced):
        assert not reference.startswith(("http", "//", "data:")), reference
        assert (STATIC_DIR / reference).is_file(), reference


def test_both_faces_are_shipped_in_both_weights() -> None:
    """`ui-context.md` uses Plex Sans 400 and 500 and Plex Mono 400 and 500.

    Plex Mono in particular is chosen because it has genuinely good tabular
    figures, which this interface depends on more than anything else.
    """
    names = {path.name for path in FONTS_DIR.glob("*.woff2")}
    assert names == {
        "IBMPlexSans-Regular.woff2",
        "IBMPlexSans-Medium.woff2",
        "IBMPlexMono-Regular.woff2",
        "IBMPlexMono-Medium.woff2",
    }
    assert (FONTS_DIR / "OFL.txt").is_file(), "the SIL Open Font License must ship with the fonts"


# --------------------------------------------------------------------------- #
# Tokens
# --------------------------------------------------------------------------- #


def test_every_palette_token_is_declared_exactly_once() -> None:
    text = TOKENS_CSS.read_text(encoding="utf-8")
    for token in PALETTE_TOKENS:
        declarations = re.findall(rf"^\s*{re.escape(token)}\s*:", text, re.M)
        assert len(declarations) == 1, f"{token} declared {len(declarations)} times"


def test_the_type_scale_matches_the_ui_context_table() -> None:
    text = TOKENS_CSS.read_text(encoding="utf-8")
    for token, size in TYPE_SIZES.items():
        assert re.search(rf"{re.escape(token)}\s*:\s*{re.escape(size)}\s*;", text), token


def test_radius_encodes_depth_rather_than_decoration() -> None:
    """4px inline, 8px on panels, 0 on table rows."""
    text = TOKENS_CSS.read_text(encoding="utf-8")
    assert "--radius-inline: 4px;" in text
    assert "--radius-panel: 8px;" in text
    assert "--radius-row: 0;" in text


def test_there_are_no_shadows_anywhere() -> None:
    """Separation comes from the hairline and the surface step.

    `box-shadow` is permitted only as a focus treatment, where it is a ring rather
    than a shadow; the console uses `outline` for that and so declares none at
    all.
    """
    for path, text in stylesheets().items():
        for selector, block in _rules(text):
            for name, value in _declarations(block):
                if name in ("box-shadow", "text-shadow") and value.lower() != "none":
                    pytest.fail(f"{path.name}: {selector} declares {name}: {value}")


# --------------------------------------------------------------------------- #
# Quality floor
# --------------------------------------------------------------------------- #


def test_the_focus_ring_is_visible_and_never_suppressed() -> None:
    """`outline: none` looks like the requirement was met and leaves a keyboard
    operator with no signal about where they are on the page."""
    visible = False
    for path, text in stylesheets().items():
        for selector, block in _rules(text):
            declarations = dict(_declarations(block))
            outline = declarations.get("outline", "").strip().lower()
            if ":focus" in selector and outline in ("none", "0"):
                pytest.fail(f"{path.name}: {selector} suppresses the focus ring")
            if ":focus-visible" in selector and outline not in ("", "none", "0"):
                visible = True
    assert visible, "no :focus-visible rule declares a visible outline"


def test_every_control_on_the_page_is_reachable_by_keyboard() -> None:
    """Tabbing has to reach the pane switcher and the three commands.

    Asserted on the markup: anchors carry a real `href` — a `<a>` without one is
    not focusable — and no interactive element is removed from the tab order with
    a negative `tabindex`. The panes themselves carry `tabindex="-1"` on purpose:
    that makes them programmatically focusable as skip-link targets without
    putting a non-interactive region into the tab sequence.
    """
    markup = TEMPLATE_PATH.read_text(encoding="utf-8")
    anchors = re.findall(r"<a\b([^>]*)>", markup)
    assert anchors
    for attributes in anchors:
        assert "href=" in attributes, attributes
        assert "tabindex" not in attributes, attributes
    for attributes in re.findall(r"<button\b([^>]*)>", markup):
        assert 'tabindex="-1"' not in attributes, attributes


def test_reduced_motion_drops_the_only_animation_there_is() -> None:
    """The 200ms flash on a changed value is the only motion permitted anywhere,
    and `prefers-reduced-motion: reduce` drops even that."""
    css = CONSOLE_CSS.read_text(encoding="utf-8")
    assert "@media (prefers-reduced-motion: reduce)" in css
    reduced = css.split("@media (prefers-reduced-motion: reduce)", 1)[1]
    assert "animation: none" in reduced


def test_there_are_no_entrance_animations_or_hover_lifts() -> None:
    """Continuously animating numbers hide real changes among fake ones."""
    css = CONSOLE_CSS.read_text(encoding="utf-8")
    animations = set(re.findall(r"@keyframes\s+([\w-]+)", css))
    assert animations == {"flash"}
    assert "transform" not in css


def test_the_layout_declares_the_1024px_floor() -> None:
    """Usable down to a 1024px window, with no horizontal scroll on the page.

    Wide content scrolls inside its own container instead — `.table-scroll` — so a
    ten-column history table cannot push the status band off the screen.
    """
    tokens = TOKENS_CSS.read_text(encoding="utf-8")
    css = CONSOLE_CSS.read_text(encoding="utf-8")
    assert "--min-width: 1024px;" in tokens
    assert "min-width: var(--min-width);" in css
    assert "overflow-x: auto;" in css


# --------------------------------------------------------------------------- #
# Serving
# --------------------------------------------------------------------------- #


def test_the_placeholder_appears_exactly_once_in_the_template() -> None:
    """The substitution has one site, so it cannot half-apply.

    The placeholder is the real default value rather than a `{{ mode }}` marker,
    which keeps `templates/index.html` a valid page that opens in a browser on its
    own — and means a second occurrence would silently produce a page in two
    modes at once.
    """
    markup = TEMPLATE_PATH.read_text(encoding="utf-8")
    assert markup.count(MODE_PLACEHOLDER) == 1


def test_the_page_and_its_assets_are_served_from_this_process(
    seeded_db: Path, seed_clock: Any
) -> None:
    app = create_app(_StubConfig("paper"), db_path=seeded_db, clock=seed_clock)
    try:
        mounts = {getattr(route, "path", None) for route in app.routes}
        assert "/" in mounts
        assert "/static" in mounts
    finally:
        app.state.reader.close()


def test_the_page_links_only_to_assets_this_process_serves() -> None:
    markup = TEMPLATE_PATH.read_text(encoding="utf-8")
    for href in re.findall(r'<link\b[^>]*href="([^"]+)"', markup):
        assert href.startswith("/static/"), href
        assert (STATIC_DIR / href.removeprefix("/static/")).is_file(), href


def test_the_page_carries_exactly_one_script_and_no_inline_handler(
) -> None:
    """Spec 23 adds `console.js` and nothing else may follow it.

    One script tag, `src`-ed from `/static`, deferred, and empty — an inline body
    would be markup the stylesheet-and-script separation cannot check and the
    served page would carry logic the file on disk does not. No `on*` attribute
    anywhere: an inline handler is a second place behaviour lives, and it is the
    one place a Content-Security-Policy could never allow.

    The pane switcher stays CSS on `:target`, which is keyboard reachable and
    bookmarkable without any script, so a page whose script failed to load still
    navigates. What it does not do is offer a command: the three buttons carry
    `disabled` in the served markup and `console.js` enables them.
    """
    markup = TEMPLATE_PATH.read_text(encoding="utf-8")
    scripts = re.findall(r"<script\b([^>]*)>(.*?)</script>", markup, re.S)
    assert len(scripts) == 1, scripts
    attributes, body = scripts[0]
    assert 'src="/static/console.js"' in attributes
    assert "defer" in attributes
    assert body.strip() == ""
    assert not re.search(r"\son[a-z]+\s*=", markup, re.I)
    commands = [a for a in re.findall(r"<button\b([^>]*)>", markup) if "data-command" in a]
    assert len(commands) == 3, commands
    for attributes in commands:
        assert "disabled" in attributes, attributes


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #


def _visible(markup: str) -> str:
    """The markup a browser acts on: comments removed."""
    return re.sub(r"<!--.*?-->", " ", markup, flags=re.S)


def _strip_comments(path: Path, text: str) -> str:
    if path.suffix == ".html":
        return _visible(text)
    return re.sub(r"/\*.*?\*/", " ", text, flags=re.S)


def _rules(text: str) -> list[tuple[str, str]]:
    """(selector, declaration block) pairs, descending into at-rule blocks."""
    stripped = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    found: list[tuple[str, str]] = []

    def scan(chunk: str) -> None:
        position = 0
        while True:
            opened = chunk.find("{", position)
            if opened == -1:
                return
            prelude = chunk[position:opened].strip()
            depth = 1
            index = opened + 1
            while index < len(chunk) and depth:
                if chunk[index] == "{":
                    depth += 1
                elif chunk[index] == "}":
                    depth -= 1
                index += 1
            block = chunk[opened + 1 : index - 1]
            if prelude.startswith("@") and "{" in block:
                scan(block)
            else:
                found.append((prelude, block))
            position = index

    scan(stripped)
    return found


def _declarations(block: str) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for statement in block.split(";"):
        if ":" not in statement or "{" in statement:
            continue
        name, _, value = statement.partition(":")
        pairs.append((name.strip().lower(), value.strip()))
    return pairs


def _touches_the_frame(selector: str) -> bool:
    lowered = selector.lower()
    return any(token in lowered for token in ("html", "body", ":root", ".frame", ".viewport"))
