"""The dashboard's look and page shell (#401, part 2 of #397).

Colours, fonts and the HTML around every page live here, so the desk, operations and
decisions pages can't drift apart. Fonts are IBM Plex (SIL Open Font License, see
static/fonts/LICENSE.txt), self-hosted: generate.py copies them beside the pages, so the
public page loads nothing from a third party. Only the Latin-1 subset of the four faces the
CSS uses is shipped; other characters (arrows, for one) fall back to the system font.

Stdlib only, no JavaScript (#26).
"""
from __future__ import annotations

import html
import shutil
from pathlib import Path

FONTS_SRC = Path(__file__).resolve().parent / "static" / "fonts"
FONTS_DIR = "fonts"          # beside the pages, so the pages link fonts/<file>
REFRESH_SECONDS = 300        # an open page reloads itself; plain HTML, no script (#26, #351)

# (family, weight, file). Only the faces the CSS below uses.
FONTS = (
    ("IBM Plex Sans", 400, "IBMPlexSans-Regular-Latin1.woff2"),
    ("IBM Plex Sans", 600, "IBMPlexSans-SemiBold-Latin1.woff2"),
    ("IBM Plex Mono", 400, "IBMPlexMono-Regular-Latin1.woff2"),
    ("IBM Plex Sans Condensed", 600, "IBMPlexSansCondensed-SemiBold-Latin1.woff2"),
)
FONT_FILES = tuple(f for _, _, f in FONTS) + ("LICENSE.txt",)
# The Latin-1 subset's range, from IBM's split CSS (@ibm/plex-sans fonts/split/woff2).
LATIN1 = ("U+0000, U+000D, U+0020-007E, U+00A0-00FF, U+0131, U+0152-0153, U+02C6, U+02DA, "
          "U+02DC, U+2013-2014, U+2018-201A, U+201C-201E, U+2020-2022, U+2026, U+2030, "
          "U+2039-203A, U+2044, U+20AC, U+2122, U+2212, U+FB01-FB02")

# The pages, in footer order: (file, name). The authority map (#410) joins when it lands.
PAGES = (("index.html", "Desk"), ("operations.html", "Operations"), ("decisions.html", "Decisions"))

# #397's palette: paper, ink, agents blue, owner amber, and red for live marks and blocks only.
PALETTE = {"paper": "#F4F3EE", "ink": "#1B1B18", "muted": "#66655E", "line": "#D8D6CC",
           "card": "#FBFAF6", "agent": "#1F4FB8", "owner": "#A35A00", "red": "#C2361B",
           "quiet": "#8B8A82"}

FONT_FACES = "\n".join(
    f'@font-face {{ font-family:"{fam}"; font-style:normal; font-weight:{w}; font-display:swap;'
    f' src:url("{FONTS_DIR}/{f}") format("woff2"); unicode-range:{LATIN1}; }}'
    for fam, w, f in FONTS)

CSS = FONT_FACES + "\n:root { " + " ".join(f"--{k}:{v};" for k, v in PALETTE.items()) + """
  --sans:"IBM Plex Sans", system-ui, -apple-system, "Segoe UI", Helvetica, Arial, sans-serif;
  --cond:"IBM Plex Sans Condensed", "IBM Plex Sans", "Arial Narrow", sans-serif;
  --mono:"IBM Plex Mono", ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
* { box-sizing:border-box; }
html { background:var(--paper); }
body { margin:0; padding:20px 16px 32px; background:var(--paper); color:var(--ink);
  font:15px/1.5 var(--sans); }
main, header.mast, footer.foot { max-width:1100px; margin:0 auto; }
main { overflow-wrap:anywhere; }
header.mast { display:flex; flex-wrap:wrap; align-items:baseline; gap:4px 16px;
  border-bottom:2px solid var(--ink); padding-bottom:6px; margin-bottom:8px; }
header.mast > span { min-width:0; overflow-wrap:anywhere; }
header.mast .name { font:600 13px/1 var(--cond); letter-spacing:.08em; text-transform:uppercase; }
h1 { font:600 26px/1.15 var(--cond); margin:12px 0 4px; letter-spacing:.01em; }
h2 { font:600 18px/1.2 var(--cond); margin:32px 0 8px; padding-top:6px;
  border-top:1px solid var(--line); text-transform:uppercase; letter-spacing:.05em; }
h3 { font:600 15px/1.3 var(--sans); margin:18px 0 6px; }
a { color:var(--ink); text-decoration:underline; text-decoration-color:var(--quiet);
  text-underline-offset:2px; }
a:hover { text-decoration-color:var(--ink); }
.muted { color:var(--muted); }
code, .mono, .num, .stamp { font-family:var(--mono); font-size:13px; }
.needs { display:flex; flex-wrap:wrap; gap:8px; margin:16px 0 0; }
.needs div { background:var(--card); border:1px solid var(--line); padding:8px 12px; }
.needs b { font:600 20px/1 var(--cond); margin-right:6px; }
.needs .hot { border-color:var(--owner); }
ol.inbox { margin:0; padding-left:24px; }
ol.inbox li { padding:4px 0; border-bottom:1px solid var(--line); }
ol.inbox li::marker { color:var(--owner); font-weight:600; }
ol.inbox li.k-blocked::marker { color:var(--red); }
.scroll { overflow-x:auto; }
.scroll, .scroll * { overflow-wrap:normal; }
table { border-collapse:collapse; width:100%; }
th, td { text-align:left; padding:6px 10px 6px 0; border-bottom:1px solid var(--line); vertical-align:top; }
th { font:600 12px/1.3 var(--cond); color:var(--muted); text-transform:uppercase;
  letter-spacing:.05em; white-space:nowrap; }
.pill { display:inline-block; padding:0 8px; font:600 12px/1.6 var(--cond); letter-spacing:.04em;
  text-transform:uppercase; color:#fff; white-space:nowrap; }
.s-active { background:var(--agent); } .s-idle { background:var(--owner); }
.s-blocked { background:var(--red); } .s-stopped { background:var(--quiet); }
.num { text-align:right; white-space:nowrap; }
table.narrow { width:auto; min-width:240px; }
.method { max-width:720px; font-size:13px; }
table.grid td { min-width:160px; }
.now { font-weight:600; }
.id { white-space:nowrap; }
details summary { cursor:pointer; margin:12px 0 4px; color:var(--muted); }
.pointer { margin:28px 0 0; padding:10px 12px; border-left:3px solid var(--agent); background:var(--card); }
footer.foot { margin-top:40px; padding-top:8px; border-top:2px solid var(--ink);
  display:flex; flex-wrap:wrap; gap:4px 18px; font:600 13px/1.6 var(--cond);
  text-transform:uppercase; letter-spacing:.06em; }
footer.foot .here { text-decoration:none; color:var(--muted); }
"""


def esc(x) -> str:
    return html.escape("" if x is None else str(x))


def nav(current: str) -> str:
    """Links to every page; the current one is marked, not linked away from."""
    links = []
    for file, name in PAGES:
        if file == current:
            links.append(f'<span class="here" aria-current="page">{esc(name)}</span>')
        else:
            links.append(f'<a href="{esc(file)}">{esc(name)}</a>')
    return "".join(links)


def page(current: str, title: str, repo: str, built: str, body: str) -> str:
    """One whole page in the shared shell: head (noindex, refresh, CSS), masthead, the body,
    and the footer linking every page."""
    name = dict(PAGES)[current]
    return "\n".join([
        '<!doctype html><html lang="en"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        '<meta name="robots" content="noindex, nofollow">',  # published publicly; see #33
        f'<meta http-equiv="refresh" content="{REFRESH_SECONDS}">',
        f"<title>{esc(name)} · {esc(title)} · {esc(repo)}</title><style>{CSS}</style></head><body>",
        f'<header class="mast"><span class="name">productswarm · {esc(name)}</span>'
        f'<span class="muted">{esc(repo)} · built <span class="stamp">{esc(built)}</span></span></header>',
        f"<main>{body}</main>",
        f'<footer class="foot">{nav(current)}</footer>',
        "</body></html>\n",
    ])


def copy_fonts(out_dir: Path) -> int:
    """Copy the font files (and their licence) into out_dir/fonts. Returns the bytes copied."""
    dest = Path(out_dir) / FONTS_DIR
    dest.mkdir(parents=True, exist_ok=True)
    size = 0
    for f in FONT_FILES:
        shutil.copyfile(FONTS_SRC / f, dest / f)
        size += (dest / f).stat().st_size
    return size
