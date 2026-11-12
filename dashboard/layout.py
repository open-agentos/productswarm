"""The dashboard's look and page shell (#401, part 2 of #397).

Colours, fonts and the HTML around every page live here, so the desk, operations and
decisions pages can't drift apart. Fonts are IBM Plex (SIL Open Font License, see
static/fonts/LICENSE.txt), self-hosted: generate.py copies them beside the pages, so the
public page loads nothing from a third party. Only the Latin-1 subset of the four faces the
CSS uses is shipped; other characters (arrows, for one) fall back to the system font.

Stdlib only. Every page carries a Content-Security-Policy; only the desk carries a script,
the live refresh (live.py, #411, option 2 of #396), and the policy allows it by hash alone.
"""
from __future__ import annotations

import datetime as dt
import html
import shutil
from pathlib import Path

import live

FONTS_SRC = Path(__file__).resolve().parent / "static" / "fonts"
FONTS_DIR = "fonts"          # beside the pages, so the pages link fonts/<file>
REFRESH_SECONDS = 300        # an open page reloads itself, script or not (#351); the desk also polls (#411)

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

# The pages, in footer order: (file, name).
PAGES = (("bridge.html", "Bridge"), ("commissions.html", "Commissions"), ("agents.html", "Agents"),
         ("index.html", "Desk"), ("operations.html", "Operations"), ("decisions.html", "Decisions"),
         ("authority.html", "Authority"))

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
header.mast .live { background:var(--red); color:#fff; padding:0 8px; font:600 12px/1.6 var(--cond);
  letter-spacing:.1em; }
header.mast .owner { color:var(--owner); }
header.mast .owner a { color:var(--owner); text-decoration-color:var(--owner); }
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
ul.findings { margin:0 0 10px; padding-left:20px; max-width:760px; }
ul.findings li { padding:2px 0; }
table.precedent { width:auto; }
table.precedent th, table.precedent td { padding:4px 6px; }
table.precedent td.num { min-width:34px; }
.pointer { margin:28px 0 0; padding:10px 12px; border-left:3px solid var(--agent); background:var(--card); }
.desk { margin:16px 0 0; }
.desk .band { display:flex; flex-wrap:wrap; align-items:baseline; gap:4px 14px; padding:10px 14px;
  background:var(--ink); color:var(--paper); font:600 14px/1.4 var(--cond);
  text-transform:uppercase; letter-spacing:.05em; }
.desk .band a { color:var(--paper); text-decoration-color:var(--quiet); }
.desk .band .q { text-transform:none; letter-spacing:0; font:600 16px/1.3 var(--sans); flex:1 1 240px; }
.desk .band .live { background:var(--red); color:#fff; padding:0 8px; letter-spacing:.1em; }
.desk .seats { display:grid; grid-template-columns:repeat(auto-fit, minmax(220px, 1fr));
  gap:1px; background:var(--line); border:1px solid var(--line); border-top:0; }
.desk .seat { background:var(--card); padding:12px 14px; min-width:0; }
.desk .seat.up { box-shadow:inset 0 3px 0 var(--agent); }
.desk .who { font:600 12px/1.3 var(--cond); text-transform:uppercase; letter-spacing:.05em; }
.desk .who .muted { text-transform:none; letter-spacing:0; font-family:var(--sans); }
.desk .reco { font:600 24px/1.15 var(--cond); color:var(--agent); margin:8px 0 4px; }
.desk .reco.none { color:var(--quiet); font-size:18px; }
.desk .swing { font:600 12px/1.3 var(--cond); text-transform:uppercase; letter-spacing:.04em;
  color:var(--muted); }
.desk blockquote { margin:8px 0 6px; font-size:14px; }
.desk .when { font:13px/1.4 var(--mono); }
.desk .bar { display:flex; align-items:center; gap:12px; padding:10px 14px; background:var(--card);
  border:1px solid var(--line); border-top:0; font:600 16px/1.2 var(--cond);
  text-transform:uppercase; letter-spacing:.05em; }
.desk .marks { display:flex; gap:3px; }
.desk .marks span { width:28px; height:10px; background:var(--line); }
.desk .marks span.on { background:var(--agent); }
.floor { display:grid; grid-template-columns:repeat(auto-fill, minmax(240px, 1fr)); gap:10px; }
.floor .card { background:var(--card); border:1px solid var(--line); border-left:4px solid var(--agent);
  padding:10px 12px; }
.floor .card.s-blocked { border-left-color:var(--red); }
.floor .role { font:600 15px/1.2 var(--cond); color:var(--agent); text-transform:uppercase;
  letter-spacing:.05em; }
.floor .what { font-weight:600; margin:4px 0 2px; }
.floor .spark { display:block; margin:6px 0 2px; }
.floor .spark .bar { fill:var(--agent); } .floor .spark .zero { fill:var(--line); }
.floor .used, .idle { font-size:13px; }
.watcher ul { margin:0; padding-left:20px; font-size:14px; } .watcher .stale { color:var(--red); }
ul.trends { list-style:none; margin:0; padding:0; }
ul.trends li { display:flex; align-items:center; gap:12px; padding:8px 0;
  border-bottom:1px solid var(--line); font-size:16px; }
ul.trends li.few { color:var(--muted); }
ul.trends svg.spark { flex:none; fill:none; stroke:var(--agent); stroke-width:1.5; }
ul.trends svg.spark circle { fill:var(--agent); stroke:none; }
ol.wire { list-style:none; margin:0; padding:0; max-width:760px; }
ol.wire li { padding:6px 0; border-bottom:1px solid var(--line); font-size:16px; }
ol.wire time { font:600 14px/1 var(--cond); color:var(--muted); margin-right:8px; }
ol.wire li.ruled time, ol.wire li.lapsed time, ol.wire li.convened time { color:var(--owner); }
ol.wire li.red time { color:var(--red); }
ol.grants { list-style:none; margin:0 0 8px; padding:0; max-width:760px; }
ol.grants li { padding:6px 0; border-bottom:1px solid var(--line); font-size:16px; overflow-wrap:anywhere; }
ol.grants time { font-family:var(--mono); }
.grants-mode { margin:0 0 6px; }
h3.left, ol.grants.left a { color:var(--owner); }
ul.went { list-style:none; margin:0; padding:0; }
ul.went li { display:flex; align-items:center; gap:12px; padding:8px 0;
  border-bottom:1px solid var(--line); font-size:16px; }
.went-bar { flex:none; display:flex; width:120px; height:10px; gap:2px; background:var(--line); }
.went-bar span { min-width:3px; }
.went-bar .agents, .went-bar .record { background:var(--agent); }
.went-bar .owner, .went-bar .direction { background:var(--owner); }
.went-bar .committee { background:var(--ink); }
.went-bar .other, .went-bar .lapsed { background:var(--quiet); }
.went-bar .open, .went-bar .nothing { background:var(--line); outline:1px solid var(--quiet); outline-offset:-1px; }
.pasts { display:grid; grid-template-columns:repeat(auto-fit, minmax(260px, 1fr)); gap:12px; }
.past { background:var(--card); border:1px solid var(--line); padding:12px 14px; min-width:0; }
.past .rec { font:600 20px/1.2 var(--cond); }
.past .q { font-size:13px; color:var(--muted); }
.past blockquote { margin:8px 0; font-size:14px; }
.past .call { font:600 14px/1.3 var(--cond); text-transform:uppercase; letter-spacing:.05em;
  color:var(--agent); }
.past .call.split { color:var(--ink); }
.past ul { margin:6px 0 0; padding:0; list-style:none; font-size:13px; color:var(--muted); }
header.mast .live.stale { background:var(--quiet); }
.report .lead { font-size:17px; margin:4px 0; } .report .lead a { font-weight:600; }
.report .stamp { color:var(--muted); margin-left:6px; white-space:nowrap; }
.report .ask, .report .ask a, ol.asks a { color:var(--owner); text-decoration-color:var(--owner); }
ol.asks { margin:4px 0 8px; padding-left:22px; } ol.asks li { padding:3px 0; }
ol.asks li::marker { color:var(--owner); font-weight:600; }
.plan .scope h3 { margin:16px 0 4px; } .plan .scope h3 .muted { font:400 13px/1 var(--sans); margin-left:6px; }
.plan ul.subs, .plan ul.subs ul { list-style:none; margin:0; padding:0; }
.plan ul.subs ul { padding-left:18px; border-left:2px solid var(--line); margin:2px 0 4px 4px; }
.plan ul.subs li { padding:3px 0; overflow-wrap:anywhere; }
.plan .st { font:600 13px/1.3 var(--cond); margin-left:4px; }
.plan .st.go { color:var(--agent); } .plan .st.waiting { color:var(--ink); }
.plan .st.not_go { color:var(--owner); } .plan .st.unknown { color:var(--muted); }
.plan .pr { font:13px/1.3 var(--mono); margin-left:6px; }
.w-agent { color:var(--agent); font-weight:600; } .w-owner { color:var(--owner); font-weight:600; }
.w-other { color:var(--quiet); }
table.authority td:first-child { min-width:200px; }
footer.foot { margin-top:40px; padding-top:8px; border-top:2px solid var(--ink);
  display:flex; flex-wrap:wrap; gap:4px 18px; font:600 13px/1.6 var(--cond);
  text-transform:uppercase; letter-spacing:.06em; }
footer.foot .here { text-decoration:none; color:var(--muted); }
/* The Bridge (#926): bridge.py, after the owner's "v5 · the bridge" mock-up. */
.bridge { display:flex; flex-wrap:wrap; gap:0 28px; align-items:flex-start; }
.br-nav { flex:1 1 170px; max-width:200px; display:flex; flex-direction:column; gap:2px;
  padding:14px 0; }
.br-navi { display:flex; justify-content:space-between; gap:8px; padding:8px 10px; text-decoration:none;
  font-size:14px; }
.br-navi.here { background:#EDEBE3; font-weight:600; }
.br-nav .br-kind { padding:18px 10px 4px; margin:0; }
.br-note { font-size:13px; padding:0 10px; margin:0; }
.br-main { flex:999 1 520px; min-width:0; display:flex; flex-direction:column; gap:26px; }
.br-titlebar { display:flex; flex-wrap:wrap; align-items:baseline; gap:4px 16px; }
.br-titlebar h1 { font-size:30px; margin:12px 0 0; }
.br-status { display:grid; grid-template-columns:repeat(auto-fit, minmax(150px, 1fr)); gap:10px; }
.br-tile { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:12px 14px;
  display:flex; flex-direction:column; gap:2px; font-size:13px; }
.br-tile.hot { border-color:var(--owner); background:#FFF8EE; }
.br-tile.hot .br-big { color:var(--owner); }
.br-big { font:24px/1.2 var(--mono); } .br-big small { font-size:15px; color:var(--muted); }
.br-sub { color:var(--muted); } .br-red { color:var(--red); }
.br-colh { display:flex; flex-wrap:wrap; align-items:baseline; justify-content:space-between; gap:4px 10px;
  padding-bottom:8px; border-bottom:1px solid var(--line); font-size:13px; }
h2.br-h { font:600 20px/1.2 var(--cond); margin:0; padding:0; border:0; text-transform:none; letter-spacing:0; }
h2.br-h.owner, .br-kind.owner { color:var(--owner); }
.br-grid { display:grid; grid-template-columns:repeat(auto-fit, minmax(280px, 1fr)); gap:12px; margin-top:12px; }
.br-dec { background:#FFF8EE; border:1px solid var(--owner); border-radius:10px; padding:14px 16px;
  display:flex; flex-direction:column; gap:6px; }
.br-dec a { color:var(--owner); text-decoration-color:var(--owner); }
.br-kind { font:11px/1.4 var(--mono); letter-spacing:.06em; color:var(--muted); }
.br-kind time { font-size:11px; }
.br-title { font-weight:600; }
.br-cols { display:flex; flex-wrap:wrap; gap:26px 32px; align-items:flex-start; }
.br-left { flex:3 1 340px; min-width:0; } .br-right { flex:2 1 260px; min-width:0; display:flex;
  flex-direction:column; gap:26px; }
.br-rep { display:flex; gap:12px; padding:12px 0; border-bottom:1px solid #E4E2D9; }
.br-body { flex:1; min-width:0; display:flex; flex-direction:column; gap:2px; }
.br-body .muted { font-size:13px; }
.br-av { width:32px; height:32px; border-radius:8px; flex:none; display:flex; align-items:center;
  justify-content:center; font:12px var(--mono); background:#E1E7F5; color:var(--agent); }
.br-av.lead { background:var(--agent); color:#fff; }
.br-row { display:flex; gap:10px; align-items:baseline; padding:9px 0; border-bottom:1px solid #E4E2D9;
  font-size:14px; }
.br-row .muted { font-size:13px; }
.br-row time { flex:none; width:70px; }
.br-grow { flex:1; min-width:0; }
.br-dot { width:9px; height:9px; border-radius:50%; flex:none; align-self:center; background:var(--quiet); }
.br-dot.agent { background:var(--agent); } .br-dot.owner { background:var(--owner); }
.br-dot.red { background:var(--red); }
/* The Commissions page (#931): a list and a focus drawer shown by :target, no script. */
.owner { color:var(--owner); }
.cm-wrap { flex:999 1 520px; min-width:0; display:flex; flex-wrap:wrap; gap:24px; align-items:flex-start; }
.cm-main { flex:3 1 400px; min-width:0; }
.cm-grp { font:11px/1.4 var(--mono); letter-spacing:.06em; color:var(--muted); margin:20px 0 0;
  padding-bottom:6px; border-bottom:1px solid var(--line); }
.cm-grp.br-red { color:var(--red); } .cm-grp.owner { color:var(--owner); }
a.cm-row { display:flex; flex-wrap:wrap; gap:6px 16px; align-items:center; padding:12px 8px;
  border-bottom:1px solid #E4E2D9; text-decoration:none; color:var(--ink); }
a.cm-row:hover { background:var(--card); }
.cm-name { flex:1 1 220px; min-width:0; display:flex; flex-direction:column; } .cm-name .muted { font-size:13px; }
.cm-bars { display:flex; align-items:center; gap:8px; width:120px; }
.cm-bar { display:block; flex:1; height:5px; background:#E4E2D9; border-radius:3px; overflow:hidden; }
.cm-fill { display:block; height:100%; background:var(--agent); }
.cm-of, .cm-bar-none { font-size:12px; }
.cm-word { min-width:80px; font-size:13px; color:var(--muted); } .cm-word.br-red { color:var(--red); }
.cm-word.owner { color:var(--owner); }
.cm-aside { flex:2 1 300px; min-width:0; max-width:420px; background:var(--card); border:1px solid var(--line);
  border-radius:10px; padding:14px 18px; position:sticky; top:12px; }
.cm-drawer { display:none; } .cm-drawer:target { display:block; }
.cm-aside:has(.cm-drawer:target) .cm-pick { display:none; }
.cm-crumb { margin:4px 0 0; font-size:13px; } h2.cm-dtitle { font-size:22px; margin:2px 0 6px; }
.cm-pill { font:12px/1 var(--mono); padding:3px 8px; border-radius:999px; color:#fff; background:var(--ink); }
.cm-pill.red { background:var(--red); } .cm-pill.owner { background:var(--owner); }
.cm-pill.agent { background:var(--agent); }
.cm-sec { border-top:1px solid #E4E2D9; padding:10px 0 4px; margin:10px 0 0; }
.cm-sec .br-kind { margin:0 0 4px; }
ul.cm-list { margin:0; padding:0; list-style:none; font-size:14px; } ul.cm-list li { padding:4px 0; }
ul.cm-list li.status-failing b { color:var(--red); } ul.cm-list li.status-met b { color:var(--agent); }
ul.cm-list .st { font:600 13px/1.3 var(--cond); } ul.cm-list .st.go { color:var(--agent); }
ul.cm-list .st.not_go { color:var(--owner); }
/* The Agents page (#932): Commissions' list and drawer, with a badge per role. */
.br-av.idle { background:#EDEBE3; color:var(--muted); }
a.cm-row .br-av { align-self:flex-start; }
.ag-n { font-size:13px; min-width:80px; }
.ag-head { display:flex; gap:10px; align-items:center; margin:6px 0; } .ag-head .cm-dtitle { margin:0; }
.ag-tiles { display:grid; grid-template-columns:repeat(2, minmax(0, 1fr)); gap:8px; }
.ag-tile { background:#fff; border:1px solid #E4E2D9; border-radius:8px; padding:8px 10px; display:flex;
  flex-direction:column; gap:2px; font-size:13px; } .ag-tile .mono { font-size:18px; }
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


def built_mark(built: dt.datetime) -> str:
    """The red LIVE mark and the build time (#402). A static page can't know how old it is
    when viewed; the `datetime` attribute is there for the state.json poll (#411)."""
    t = built.astimezone(dt.timezone.utc)
    return (f'<span class="live">LIVE</span><span class="muted">built <time class="stamp" '
            f'datetime="{t.strftime("%Y-%m-%dT%H:%M:%SZ")}" title="{t.strftime("%Y-%m-%d %H:%M UTC")}">'
            f'{t.strftime("%H:%M")} UTC</time></span>')



def masthead(current: str, repo: str, built: dt.datetime, owner: str = "") -> str:
    """What's inside the page's <header>: the page name, the repo, the LIVE mark and build time,
    and `owner`, the owner's last act as HTML (#402). The desk's live refresh redraws it too
    (#411)."""
    return (f'<span class="name">productswarm · {esc(dict(PAGES)[current])}</span>'
            f'<span class="muted">{esc(repo)}</span>{built_mark(built)}{owner}')


def page(current: str, title: str, repo: str, built: dt.datetime, body: str, owner: str = "",
         live_refresh: bool = False) -> str:
    """One whole page in the shared shell: head (noindex, CSP, refresh, CSS), masthead (#402),
    the body, and the footer linking every page. With `live_refresh`, the page also carries the
    live refresh script, which polls state.json (#411); only the desk does."""
    built_at = built.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if live_refresh else None
    name = dict(PAGES)[current]
    js = live.script() if built_at else None
    box = ' data-panel="mast"' if js else ""
    return "\n".join(part for part in [
        '<!doctype html><html lang="en"><head><meta charset="utf-8">',
        f'<meta http-equiv="Content-Security-Policy" content="{live.csp(js)}">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        '<meta name="robots" content="noindex, nofollow">',  # published publicly; see #33
        f'<meta http-equiv="refresh" content="{REFRESH_SECONDS}">',
        f"<title>{esc(name)} · {esc(title)} · {esc(repo)}</title><style>{CSS}</style></head>"
        + (f'<body data-built-at="{esc(built_at)}">' if built_at else "<body>"),
        f'<header class="mast"{box}>{masthead(current, repo, built, owner)}</header>',
        f"<main>{body}</main>",
        f'<footer class="foot">{nav(current)}</footer>',
        f"<script>{js}</script>" if js else None,
        "</body></html>\n",
    ] if part is not None)


def copy_fonts(out_dir: Path) -> int:
    """Copy the font files (and their licence) into out_dir/fonts. Returns the bytes copied."""
    dest = Path(out_dir) / FONTS_DIR
    dest.mkdir(parents=True, exist_ok=True)
    size = 0
    for f in FONT_FILES:
        shutil.copyfile(FONTS_SRC / f, dest / f)
        size += (dest / f).stat().st_size
    return size
