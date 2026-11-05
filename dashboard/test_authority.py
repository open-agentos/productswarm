"""Tests for dashboard/authority.py (#410). Run: python3 -m unittest discover -s dashboard"""
import datetime as dt
import re
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import authority as a  # noqa: E402
import governance as gv  # noqa: E402

REPO = "open-agentos/productswarm"
TODAY = dt.date(2026, 11, 5)

YML = """# Who may decide what.
version: 0

identities:
  humans:
    owner: "@someone"   # a comment
  agents:
    builder: "productswarm-builder[bot]"
    reviewer: 'productswarm-reviewer[bot]'

quorum: 0.5          # fraction
consent_window: 48h

domains:

  code-conventions:
    description: Style, naming & <layout>.
    owner: agents.reviewer
    decide: [agents.builder, agents.reviewer]   # two of them
    ratify: [humans.owner]
    vote_eligible: [agents.builder, agents.ghost]
    default_shape: autonomous

  security:
    description: Auth, credentials.
    owner: humans.owner
    decide: []
    ratify: [humans.owner]
    default_shape: authoritative
    always_one_way: true
    note: Treat as one-way.
"""

INDEX = """| ID | Ruling | Domain | Shape | Status | Review by |
|---|---|---|---|---|---|
| [GOV-0001](decisions/GOV-0001-a.md) | a | security | authoritative | in-force | 2027-01-31 |
| [GOV-0002](decisions/GOV-0002-b.md) | b | security | authoritative | in-force | 2026-10-01 |
| [GOV-0003](decisions/GOV-0003-c.md) | c | security | authoritative | superseded | 2027-01-31 |
| [GOV-0004](decisions/GOV-0004-d.md) | d | nowhere | advice | in-force | 2027-01-31 |
"""


def records(text=INDEX):
    return gv.recent_records(gv.parse_index(text), TODAY, n=999)


def domain_names(text: str) -> list[str]:
    """The domain keys, read independently of authority.read(): two-space keys under
    `domains:`."""
    body = text.split("\ndomains:", 1)[1]
    return re.findall(r"^  ([A-Za-z0-9_-]+):\s*$", body, re.M)


class ReadTest(unittest.TestCase):
    def test_reads_the_known_shape(self):
        doc = a.read(YML)
        self.assertEqual(doc["version"], 0)
        self.assertEqual(doc["quorum"], 0.5)
        self.assertEqual(doc["consent_window"], "48h")
        self.assertEqual(doc["identities"]["humans"]["owner"], "@someone")
        self.assertEqual(doc["identities"]["agents"]["reviewer"], "productswarm-reviewer[bot]")
        cc = doc["domains"]["code-conventions"]
        self.assertEqual(cc["decide"], ["agents.builder", "agents.reviewer"])
        self.assertEqual(doc["domains"]["security"]["decide"], [])
        self.assertIs(doc["domains"]["security"]["always_one_way"], True)

    def test_rejects_what_it_doesnt_know(self):
        for bad in ("domains:\n  x:\n    decide:\n      - agents.builder\n",   # block list
                    "domains:\n  x:\n    note: |\n      text\n",                  # block scalar
                    "domains:\n  x:\n      owner: humans.owner\n    decide: []\n",  # bad dedent
                    "a: 1\na: 2\n",                                                # duplicate
                    "  a: 1\n",                                                    # indented root
                    "domains: [unclosed\n",
                    "just text\n"):
            with self.assertRaises(ValueError, msg=bad):
                a.domains(a.read(bad))

    def test_domains_need_their_fields(self):
        for bad in ("version: 0\n",
                    "domains:\n  x:\n    decide: []\n",                          # no owner/shape
                    "domains:\n  x:\n    owner: humans.owner\n    default_shape: advice\n"
                    "    decide: agents.builder\n"):                              # not a list
            with self.assertRaises(ValueError, msg=bad):
                a.domains(a.read(bad))


class BuildTest(unittest.TestCase):
    def test_model(self):
        m = a.build(YML, records())
        self.assertIsNone(m["error"])
        self.assertEqual([d["name"] for d in m["domains"]], ["code-conventions", "security"])
        cc, sec = m["domains"]
        self.assertEqual([(i["kind"], i["name"]) for i in cc["decide"]],
                         [("agent", "builder"), ("agent", "reviewer")])
        self.assertEqual(cc["owner"]["kind"], "agent")
        self.assertEqual(sec["owner"], {"kind": "owner", "name": "owner", "login": "@someone"})
        self.assertEqual(cc["vote_eligible"][1], {"kind": "other", "name": "agents.ghost", "login": None})
        self.assertEqual(sec["records"], ["GOV-0001", "GOV-0002"])   # in force only
        self.assertEqual(sec["passed"], ["GOV-0002"])
        self.assertEqual(cc["records"], [])
        self.assertEqual(m["elsewhere"], ["nowhere"])

    def test_missing_or_unreadable_file(self):
        self.assertIn("can't read governance/jurisdictions.yml", a.build(None, [])["error"])
        self.assertIn("can't read governance/jurisdictions.yml", a.build("domains: |\n", [])["error"])


class RenderTest(unittest.TestCase):
    def test_page(self):
        html = a.render(a.build(YML, records()), REPO)
        self.assertIn('<tr id="code-conventions"><td><b>code-conventions</b>', html)
        self.assertIn('<span class="w-agent" title="productswarm-builder[bot]">builder</span>', html)
        self.assertIn('<span class="w-owner" title="@someone">owner</span>', html)
        self.assertIn('<span class="w-other">agents.ghost</span>', html)
        self.assertIn("Style, naming &amp; &lt;layout&gt;.", html)
        self.assertIn("always one-way", html)
        self.assertIn("Treat as one-way.", html)
        self.assertIn("nobody: ask", html)
        self.assertIn('<a href="decisions.html">2 in force</a>', html)
        self.assertIn("review date passed: GOV-0002", html)
        self.assertIn("domains the file doesn't list: nowhere", html)
        self.assertIn("quorum of 0.5", html)

    def test_error_is_muted_and_nothing_guessed(self):
        html = a.render(a.build("domains: |\n", []), REPO)
        self.assertIn('<p class="muted">can&#x27;t read governance/jurisdictions.yml', html)
        self.assertNotIn("<table", html)

    def test_every_domain_in_the_real_file_is_on_the_page(self):
        text = a.JURISDICTIONS.read_text(encoding="utf-8")
        names = domain_names(text)
        self.assertGreater(len(names), 5)
        html = a.render(a.build(text, records(gv.INDEX.read_text(encoding="utf-8"))), REPO)
        self.assertNotIn("can&#x27;t read", html)
        for name in names:
            self.assertIn(f'<tr id="{name}"><td><b>{name}</b>', html, f"{name} missing")


if __name__ == "__main__":
    unittest.main()
