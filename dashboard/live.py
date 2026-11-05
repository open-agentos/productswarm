"""The desk's live refresh (#411, part 12 of #397; option 2 of #396).

An open desk page fetches `state.json` every 15 seconds and redraws its panels without a
reload. The panels are drawn once, in Python, as they always were: `tree()` turns each
panel's HTML into a node tree for `state.json["desk"]`, and the inline script (`poll.js`)
turns the tree back into DOM nodes with `createElement`, `setAttribute` and text nodes. So
there's one renderer, and the browser never parses HTML, uses `innerHTML` or `eval`.

A node is a string (text) or `[tag, {attr: value}, child, ...]`. Only the tags and
attributes below may appear, and links only to https URLs, a page beside this one or a
fragment; `tree()` raises on anything else, and the script refuses it again, so a panel
that would carry something new stays as the static page drew it.

The page stays complete with JavaScript off: the script only replaces what's already there.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
from html.parser import HTMLParser
from pathlib import Path

POLL_JS = Path(__file__).resolve().parent / "poll.js"
EVERY_SECONDS = 15        # how often an open desk fetches state.json
STALE_MINUTES = 15        # older data greys the LIVE mark (#402)

TAGS = frozenset(("a", "b", "blockquote", "br", "code", "details", "div", "em", "h1", "h2",
                  "h3", "i", "li", "ol", "p", "section", "small", "span", "strong", "summary",
                  "table", "tbody", "td", "th", "thead", "time", "tr", "ul"))
SVG_TAGS = frozenset(("svg", "circle", "polyline", "rect", "title"))
ATTRS = frozenset(("class", "href", "title", "role", "aria-label", "aria-current",
                   "aria-hidden", "datetime", "style", "open", "colspan", "rowspan",
                   "width", "height", "viewBox", "x", "y", "cx", "cy", "r", "points"))
VOID = frozenset(("br",))
# html.parser lowercases attribute names; SVG's are case-sensitive.
SVG_CASE = {"viewbox": "viewBox"}
# https anywhere, a page beside this one (operations.html#x), or a fragment (#x).
SAFE_URL = r"^(https://|[A-Za-z0-9_-]+\.html(#[A-Za-z0-9_-]*)?$|#[A-Za-z0-9_-]*$)"


class _Tree(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root: list = []
        self.stack: list[list] = []   # open elements; each is [tag, attrs, *children]
        self.svg = 0                  # depth inside <svg>

    def _children(self) -> list:
        return self.stack[-1] if self.stack else self.root

    def handle_starttag(self, tag, attrs, closed=False):
        in_svg = self.svg or tag == "svg"
        if tag not in (SVG_TAGS if in_svg else TAGS):
            raise ValueError(f"tag <{tag}> isn't allowed in a live panel")
        out = {}
        for k, v in attrs:
            k = SVG_CASE.get(k, k) if in_svg else k
            v = "" if v is None else v
            if k not in ATTRS:
                raise ValueError(f"attribute {k} on <{tag}> isn't allowed in a live panel")
            if k == "href" and not re.match(SAFE_URL, v):
                raise ValueError(f"link {v!r} isn't allowed in a live panel")
            out[k] = v
        node = [tag, out]
        self._children().append(node)
        if closed or tag in VOID:
            return
        self.stack.append(node)
        if self.svg or tag == "svg":
            self.svg += 1

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs, closed=True)

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        if not self.stack or self.stack[-1][0] != tag:
            raise ValueError(f"unbalanced </{tag}> in a live panel")
        self.stack.pop()
        if self.svg:
            self.svg -= 1

    def handle_data(self, data):
        kids = self._children()
        if len(kids) > (2 if self.stack else 0) and isinstance(kids[-1], str):
            kids[-1] += data
        else:
            kids.append(data)

    def handle_comment(self, data):
        pass

    def handle_decl(self, decl):
        raise ValueError("a declaration isn't allowed in a live panel")

    def unknown_decl(self, data):
        raise ValueError("a declaration isn't allowed in a live panel")

    def handle_pi(self, data):
        raise ValueError("a processing instruction isn't allowed in a live panel")


def tree(fragment: str) -> list:
    """A panel's HTML as a list of nodes. Raises ValueError on a tag, attribute or link
    outside the lists above, or on unbalanced tags."""
    p = _Tree()
    p.feed(fragment)
    p.close()
    if p.stack:
        raise ValueError(f"unclosed <{p.stack[-1][0]}> in a live panel")
    return p.root


def trees(panels: dict[str, str]) -> dict[str, list | None]:
    """Each panel's node tree, by name. A panel that can't be one is None, so an open page
    keeps that panel as it was drawn until its next reload; the build doesn't fail."""
    out = {}
    for name, fragment in panels.items():
        try:
            out[name] = tree(fragment)
        except ValueError:
            out[name] = None
    return out


def script() -> str:
    """poll.js with its settings and the allow lists filled in: exactly what goes between
    <script> and </script>, so its hash is the one the page's CSP names."""
    allow = {"tags": {t: 1 for t in sorted(TAGS)}, "svg": {t: 1 for t in sorted(SVG_TAGS)},
             "attrs": {a: 1 for a in sorted(ATTRS)}}
    js = (POLL_JS.read_text(encoding="utf-8")
          .replace("/*ALLOW*/null", json.dumps(allow, separators=(",", ":")))
          .replace("/*SAFE_URL*/null", "new RegExp(" + json.dumps(SAFE_URL) + ")")
          .replace("/*EVERY*/0", str(EVERY_SECONDS * 1000))
          .replace("/*STALE*/0", str(STALE_MINUTES * 60 * 1000)))
    if "</" in js:
        raise ValueError("poll.js can't contain '</'")
    return js


def script_hash(js: str) -> str:
    """The CSP source for an inline script: 'sha256-<base64 digest>'."""
    return "'sha256-" + base64.b64encode(hashlib.sha256(js.encode("utf-8")).digest()).decode() + "'"


def csp(js: str | None) -> str:
    """The page's Content-Security-Policy: same-origin fonts and fetches, inline styles
    (the page's <style> and the precedent table's cell shading), and no script but the one
    whose hash is given."""
    scripts = script_hash(js) if js else "'none'"
    return ("default-src 'none'; "
            f"script-src {scripts}; "
            "style-src 'unsafe-inline'; "
            "font-src 'self'; "
            "connect-src 'self'; "
            "base-uri 'none'; "
            "form-action 'none'")
