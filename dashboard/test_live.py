"""Tests for the desk's live refresh: dashboard/live.py and poll.js (#411).
Run: python3 -m unittest discover -s dashboard"""
import base64
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import committees  # noqa: E402
import floor  # noqa: E402
import grants  # noqa: E402
import generate as g  # noqa: E402
import live  # noqa: E402
import precedent  # noqa: E402
import state as st  # noqa: E402
import trends  # noqa: E402
from test_floor import model as floor_model  # noqa: E402
from test_generate import REPO, ev  # noqa: E402


def desk_model():
    return floor_model({"a": [ev("a", "working_on", 40, issue=1)],
                        "b": [ev("b", "heartbeat", 2, issue=392, tools=["Edit"])]})


def script_of(page: str) -> str:
    found = re.findall(r"<script>(.*?)</script>", page, re.S)
    assert len(found) == 1, len(found)
    return found[0]


def csp_of(page: str) -> dict[str, list[str]]:
    content = re.search(r'<meta http-equiv="Content-Security-Policy" content="([^"]*)">', page)[1]
    return {d.split()[0]: d.split()[1:] for d in content.split("; ")}


class TreeTest(unittest.TestCase):
    def test_elements_text_and_svg(self):
        t = live.tree('<p class="x">a &amp; <a href="https://github.com/o/r/issues/1">#1</a>'
                      '<br></p><svg viewBox="0 0 2 2" width="2"><rect x="1" y="0"/><title>t</title></svg>')
        self.assertEqual(t, [
            ["p", {"class": "x"}, "a & ", ["a", {"href": "https://github.com/o/r/issues/1"}, "#1"],
             ["br", {}]],
            ["svg", {"viewBox": "0 0 2 2", "width": "2"}, ["rect", {"x": "1", "y": "0"}],
             ["title", {}, "t"]]])

    def test_text_stays_text(self):
        # Escaped markup in repo text comes back as the characters, never as an element.
        self.assertEqual(live.tree("<span>&lt;script&gt;x&lt;/script&gt;</span>"),
                         [["span", {}, "<script>x</script>"]])

    def test_boolean_attribute_and_local_links(self):
        self.assertEqual(live.tree('<details open><summary>s</summary></details>'
                                   '<a href="decisions.html#x">d</a><a href="#y">y</a>'),
                         [["details", {"open": ""}, ["summary", {}, "s"]],
                          ["a", {"href": "decisions.html#x"}, "d"], ["a", {"href": "#y"}, "y"]])

    def test_refuses_what_isnt_allowed(self):
        for bad in ("<script>x</script>", "<img src=x>", "<iframe></iframe>", "<style>p{}</style>",
                    '<p onclick="x()">p</p>', '<a href="javascript:x()">a</a>',
                    '<a href="//evil.example/">a</a>', '<a href="http://x/">a</a>',
                    '<svg><foreignObject></foreignObject></svg>', "<rect></rect>",
                    "<p><b></p></b>", "<p>open", "<!DOCTYPE html>"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                live.tree(bad)

    def test_a_bad_panel_is_none_not_a_failed_build(self):
        self.assertEqual(live.trees({"ok": "<p>a</p>", "bad": "<script></script>", "empty": ""}),
                         {"ok": [["p", {}, "a"]], "bad": None, "empty": []})


class EveryPanelTest(unittest.TestCase):
    """Every panel HTML the panels' own tests draw becomes a tree, so no panel silently
    stops refreshing when its markup grows a new tag or attribute."""

    def test_panel_fixtures_convert(self):
        failures = []

        def checked(fn):
            def wrapper(*a, **k):
                out = fn(*a, **k)
                try:
                    live.tree(out)
                except ValueError as e:
                    failures.append(f"{fn.__module__}.{fn.__name__}: {e}")
                return out
            return wrapper

        patches = [mock.patch.object(floor, "render", checked(floor.render)),
                   mock.patch.object(committees, "desk", checked(committees.desk)),
                   mock.patch.object(committees, "past", checked(committees.past)),
                   mock.patch.object(trends, "render", checked(trends.render)),
                   mock.patch.object(precedent, "render", checked(precedent.render)),
                   mock.patch.object(grants, "render", checked(grants.render))]
        for p in patches:
            p.start()
        try:
            suite = unittest.defaultTestLoader.loadTestsFromNames(
                ["test_floor", "test_committees", "test_trends", "test_precedent", "test_generate",
                 "test_grants"])
            result = unittest.TestResult()
            suite.run(result)
        finally:
            for p in patches:
                p.stop()
        self.assertTrue(result.wasSuccessful(), result.failures + result.errors)
        self.assertEqual(failures, [])


class PageTest(unittest.TestCase):
    def setUp(self):
        self.m = desk_model()
        self.pages = g.render(self.m)
        self.desk = self.pages["index.html"]

    def test_csp_hash_matches_the_script(self):
        js = script_of(self.desk)
        digest = base64.b64encode(hashlib.sha256(js.encode("utf-8")).digest()).decode()
        csp = csp_of(self.desk)
        self.assertEqual(csp["script-src"], [f"'sha256-{digest}'"])   # that script, nothing else
        self.assertEqual(csp["default-src"], ["'none'"])
        self.assertEqual(csp["connect-src"], ["'self'"])
        self.assertEqual(js, live.script())

    def test_csp_comes_before_anything_it_governs(self):
        head = self.desk.split("</head>")[0]
        self.assertLess(head.index("Content-Security-Policy"), head.index("<style>"))

    def test_script_builds_nodes_never_markup_or_code(self):
        js = live.script()
        for bad in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval",
                    "Function(", "DOMParser", "createContextualFragment", "srcdoc", "import(",
                    "XMLHttpRequest", "localStorage", "cookie"):
            self.assertNotIn(bad, js, bad)
        self.assertEqual(re.findall(r'fetch\("([^"?]*)', js), ["state.json"])
        self.assertNotRegex(js, r"/\*[A-Z_]+\*/")   # every placeholder filled in
        self.assertIn('querySelectorAll("header.mast .live")', js)   # #402's mark

    def test_only_the_desk_has_a_script(self):
        for name in ("operations.html", "decisions.html"):
            self.assertNotIn("<script", self.pages[name].lower(), name)
            self.assertEqual(csp_of(self.pages[name])["script-src"], ["'none'"], name)

    def test_static_page_is_complete_without_the_script(self):
        # Each panel is drawn in full inside its box, and the meta refresh stays.
        for name, fragment in g.desk_panels(self.m).items():
            self.assertIn(f'<div data-panel="{name}">{fragment}</div>', self.desk)
        self.assertIn("<h2>On the floor</h2>", self.desk)
        self.assertIn('<meta http-equiv="refresh" content="300">', self.desk)
        self.assertIn('<body data-built-at="2026-11-02T12:00:00Z">', self.desk)

    def test_state_carries_every_box_on_the_desk(self):
        s = st.state(self.m)
        boxes = re.findall(r'data-panel="([^"]+)"', self.desk)
        self.assertEqual(sorted(s["desk"]), sorted(boxes))
        self.assertTrue(all(isinstance(t, list) for t in s["desk"].values()), s["desk"])
        self.assertEqual(s["desk"]["floor"], live.tree(g.desk_panels(self.m)["floor"]))
        self.assertEqual(json.loads(json.dumps(s)), s)


NODE = shutil.which("node")

# A fake DOM just big enough for poll.js: elements, text, fragments, two selectors,
# a fetch that serves whatever `served` holds, and a hand-cranked clock and interval.
HARNESS = r"""
const fs = require("fs");
const [scriptPath, casesPath] = process.argv.slice(2);
const js = fs.readFileSync(scriptPath, "utf8");
const cases = JSON.parse(fs.readFileSync(casesPath, "utf8"));
function el(tag, ns) {
  return { tag, ns: ns || null, attrs: {}, children: [], classes: new Set(),
    setAttribute(k, v) { this.attrs[k] = String(v); },
    getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; },
    appendChild(c) { if (c.frag) { this.children.push(...c.children); } else { this.children.push(c); } return c; },
    removeChild(c) { this.children.splice(this.children.indexOf(c), 1); },
    get firstChild() { return this.children[0] || null; },
    classList: null };
}
function dump(n) { return n.text !== undefined ? n.text : [n.tag, n.attrs, ...n.children.map(dump)]; }
(async () => {
  const out = [];
  for (const c of cases) {
    const body = el("body"); body.attrs["data-built-at"] = c.page_built_at;
    const live = el("span"); live.classList = { toggle(k, on) { on ? live.classes.add(k) : live.classes.delete(k); } };
    const panel = el("div"); panel.attrs["data-panel"] = "floor"; panel.children.push({ text: "static" });
    let now = Date.parse(c.clock), tick = null, fetched = [];
    global.Date = class extends Date { static now() { return now; } };
    global.document = {
      body, hidden: false,
      createElement: (t) => el(t), createElementNS: (ns, t) => el(t, ns),
      createTextNode: (t) => ({ text: t }), createDocumentFragment: () => Object.assign(el("#frag"), { frag: true }),
      querySelectorAll: (s) => s === "[data-panel]" ? [panel] : s === "header.mast .live" ? [live] : [],
    };
    global.fetch = (url, opts) => { fetched.push([url.split("?")[0], opts.cache]);
      return Promise.resolve({ ok: true, json: () => Promise.resolve(c.served) }); };
    global.setInterval = (fn, ms) => { tick = fn; out.interval = ms; };
    new Function(js)();
    const staleAtLoad = live.classes.has("stale");
    now += c.advance_ms; tick();
    await new Promise((r) => setTimeout(r, 0)); await new Promise((r) => setTimeout(r, 0));
    out.push({ name: c.name, staleAtLoad, stale: live.classes.has("stale"), fetched,
      panel: panel.children.map(dump), built_at: body.attrs["data-built-at"] });
  }
  console.log(JSON.stringify(out));
})();
"""


@unittest.skipUnless(NODE, "node isn't installed")
class ScriptBehaviourTest(unittest.TestCase):
    """poll.js itself, run in node against a fake DOM."""

    def run_cases(self, cases):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "poll.js").write_text(live.script(), encoding="utf-8")
            (Path(d) / "cases.json").write_text(json.dumps(cases), encoding="utf-8")
            (Path(d) / "harness.js").write_text(HARNESS, encoding="utf-8")
            r = subprocess.run([NODE, str(Path(d) / "harness.js"), str(Path(d) / "poll.js"),
                                str(Path(d) / "cases.json")], capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        return {c["name"]: c for c in json.loads(r.stdout)}

    def state(self, built_at, floor_tree):
        return {"schema": 1, "built_at": built_at, "desk": {"floor": floor_tree}}

    def test_refresh(self):
        new = [["h2", {}, "On the floor"], ["p", {"class": "x"}, "<b>not markup</b>"],
               ["svg", {"viewBox": "0 0 1 1"}, ["rect", {"x": "0"}]]]
        evil = [["p", {}, "ok"], ["script", {}, "alert(1)"]]
        bad_link = [["a", {"href": "javascript:alert(1)"}, "x"]]
        base = {"page_built_at": "2026-11-05T10:00:00Z", "clock": "2026-11-05T10:01:00Z",
                "advance_ms": 15000}
        got = self.run_cases([
            {**base, "name": "newer", "served": self.state("2026-11-05T10:01:00Z", new)},
            {**base, "name": "older", "served": self.state("2026-11-05T09:00:00Z", new)},
            {**base, "name": "script", "served": self.state("2026-11-05T10:01:00Z", evil)},
            {**base, "name": "link", "served": self.state("2026-11-05T10:01:00Z", bad_link)},
            {**base, "name": "stale", "clock": "2026-11-05T10:20:00Z",
             "served": self.state("2026-11-05T09:00:00Z", new)},
            {**base, "name": "fresh_again", "clock": "2026-11-05T10:20:00Z",
             "served": self.state("2026-11-05T10:19:00Z", new)},
        ])
        n = got["newer"]
        self.assertEqual(n["fetched"], [["state.json", "no-store"]])
        self.assertEqual(n["panel"], new)                     # redrawn as nodes; text stays text
        self.assertEqual(n["built_at"], "2026-11-05T10:01:00Z")
        self.assertFalse(n["stale"])
        self.assertEqual(got["older"]["panel"], ["static"])   # never moves backwards
        self.assertEqual(got["script"]["panel"], ["static"])  # a refused node keeps the panel
        self.assertEqual(got["link"]["panel"], ["static"])
        self.assertTrue(got["stale"]["staleAtLoad"])          # 20 minutes old: greyed
        self.assertTrue(got["stale"]["stale"])
        self.assertFalse(got["fresh_again"]["stale"])         # new data brings it back


if __name__ == "__main__":
    unittest.main()
