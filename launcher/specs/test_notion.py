"""Tests for launcher/specs/notion.py (#951): the notion backend, against a fake workspace.

No network and no real token: every request goes through FakeNotion, a `transport`.
Run: python3 run_tests.py launcher
"""
import ast
import copy
import json
import os
import re
import sys
import tempfile
import unittest
import urllib.parse
import uuid
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from specs import notion  # noqa: E402
from specs.notion import (  # noqa: E402
    NOTION_VERSION, NotionError, NotionSource, ScopeError, TokenError, load_token,
)
from specs.source import (  # noqa: E402
    Criterion, FeatureStatus, SchemaError, Spec, SpecSource,
)

TOKEN = "ntn_SECRETsecret0123456789"
PARENT = "11111111111111111111111111111111"
INIT_DB = "22222222-2222-2222-2222-222222222222"
FEAT_DB = "33333333-3333-3333-3333-333333333333"
INITIATIVE = "44444444-4444-4444-4444-444444444444"
PAGE1 = "55555555-5555-5555-5555-555555555501"
PAGE2 = "55555555-5555-5555-5555-555555555502"
PAGE3 = "55555555-5555-5555-5555-555555555503"
NOW = "2026-11-12T22:00:00+00:00"


def rt(text):
    return [{"type": "text", "text": {"content": text}, "plain_text": text}]


_ids = iter(range(1, 10**6))


def block(kind, text="", children=None, **extra):
    b = {"object": "block", "id": str(uuid.UUID(int=next(_ids))), "type": kind,
         "has_children": bool(children), kind: dict({"rich_text": rt(text)}, **extra)}
    if children:
        b["_children"] = children
    return b


def initiatives_schema():
    return {"object": "database", "id": INIT_DB, "properties": {
        "Name": {"type": "title", "title": {}},
        "Goal": {"type": "url", "url": {}},
        "Status": {"type": "status", "status": {"options": [
            {"name": n} for n in ("Planned", "Active", "Done")]}},
    }}


def features_schema():
    return {"object": "database", "id": FEAT_DB, "properties": {
        "Name": {"type": "title", "title": {}},
        "ID": {"type": "unique_id", "unique_id": {"prefix": "FEAT"}},
        "Initiative": {"type": "relation", "relation": {"database_id": INIT_DB}},
        "Status": {"type": "status", "status": {"options": [
            {"name": s.value} for s in FeatureStatus]}},
        "Issue": {"type": "url", "url": {}},
        "PR": {"type": "url", "url": {}},
        "Last synced": {"type": "date", "date": {}},
        "Owner notes": {"type": "rich_text", "rich_text": {}},   # extra columns are fine
    }}


def feature_page(pid, number, name, status, initiative=INITIATIVE, issue=None, pr=None):
    return {"object": "page", "id": pid, "url": f"https://www.notion.so/{pid.replace('-', '')}",
            "last_edited_time": "2026-11-12T20:00:00.000Z", "properties": {
                "Name": {"type": "title", "title": rt(name)},
                "ID": {"type": "unique_id", "unique_id": {"prefix": "FEAT", "number": number}},
                "Initiative": {"type": "relation", "relation": [{"id": initiative}]},
                "Status": {"type": "status", "status": {"name": status}},
                "Issue": {"type": "url", "url": issue},
                "PR": {"type": "url", "url": pr},
                "Last synced": {"type": "date", "date": None},
            }}


SPEC_BLOCKS = [
    block("paragraph", "Template intro, ignored."),
    block("heading_2", "Problem"),
    block("paragraph", "Owners can't see specs ship."),
    block("heading_2", "Scope"),
    block("bulleted_list_item", "Pull Ready features", children=[
        block("bulleted_list_item", "one issue each")]),
    block("heading_2", "Out of scope"),
    block("paragraph", "Writing spec bodies."),
    block("heading_2", "Acceptance criteria"),
    block("to_do", "Pull opens one issue per Ready feature", checked=False),
    block("to_do", "Push writes status back", checked=True),
    block("heading_2", "Notes"),
    block("paragraph", "See #937."),
]


class FakeNotion:
    """A Notion workspace as a transport. Records every request; answers the calls the
    backend is allowed to make, and fails the test on any other."""

    def __init__(self):
        self.calls = []
        self.parent_children = [
            {"object": "block", "id": "x1", "type": "paragraph", "has_children": False,
             "paragraph": {"rich_text": rt("Ready means fine to be public.")}},
            {"object": "block", "id": INIT_DB, "type": "child_database",
             "child_database": {"title": "Initiatives"}},
            {"object": "block", "id": FEAT_DB, "type": "child_database",
             "child_database": {"title": "Features"}},
        ]
        self.databases = {INIT_DB: initiatives_schema(), FEAT_DB: features_schema()}
        self.pages = {
            PAGE1: feature_page(PAGE1, 1, "Effort mix chart", "Ready"),
            PAGE2: feature_page(PAGE2, 2, "Effort mix eval", "Draft"),
            PAGE3: feature_page(PAGE3, 3, "Other initiative", "Ready",
                                initiative="66666666-6666-6666-6666-666666666666"),
        }
        self.bodies = {PAGE1: copy.deepcopy(SPEC_BLOCKS), PAGE2: [
            block("heading_2", "Problem"), block("paragraph", "No criteria yet."),
        ]}
        self.comments = {}
        self.page_size = None   # force pagination when set

    def _norm(self, s):
        return s.replace("-", "")

    def _find_block(self, bid):
        if self._norm(bid) == self._norm(PARENT):
            return self.parent_children
        for pid, blocks in self.bodies.items():
            if self._norm(pid) == self._norm(bid):
                return blocks
            stack = list(blocks)
            while stack:
                b = stack.pop()
                if b["id"] == bid:
                    return b.get("_children", [])
                stack.extend(b.get("_children", []))
        return None

    def _page(self, items, cursor, size):
        size = min(size or 100, self.page_size or 100)
        start = int(cursor or 0)
        chunk = [{k: v for k, v in i.items() if k != "_children"} for i in items[start:start + size]]
        more = start + size < len(items)
        return {"object": "list", "results": chunk, "has_more": more,
                "next_cursor": str(start + size) if more else None}

    def __call__(self, method, url, headers, body):
        parsed = urllib.parse.urlparse(url)
        assert parsed.scheme == "https" and parsed.netloc == "api.notion.com", url
        path = parsed.path
        q = dict(urllib.parse.parse_qsl(parsed.query))
        payload = json.loads(body) if body else None
        self.calls.append((method, path, q, payload, dict(headers)))
        ok = lambda d: (200, json.dumps(d).encode())  # noqa: E731

        m = re.fullmatch(r"/v1/blocks/([^/]+)/children", path)
        if method == "GET" and m:
            items = self._find_block(m.group(1))
            if items is None:
                return 404, json.dumps({"code": "object_not_found", "message": "nope"}).encode()
            return ok(self._page(items, q.get("start_cursor"), int(q.get("page_size", 100))))
        m = re.fullmatch(r"/v1/databases/([^/]+)", path)
        if method == "GET" and m:
            return ok(self.databases[m.group(1)])
        m = re.fullmatch(r"/v1/databases/([^/]+)/query", path)
        if method == "POST" and m:
            assert m.group(1) == FEAT_DB
            f = payload["filter"]
            rows = list(self.pages.values())
            if f["property"] == "Initiative":
                want = self._norm(f["relation"]["contains"])
                rows = [r for r in rows if self._norm(
                    r["properties"]["Initiative"]["relation"][0]["id"]) == want]
            elif f["property"] == "ID":
                rows = [r for r in rows
                        if r["properties"]["ID"]["unique_id"]["number"] == f["unique_id"]["equals"]]
            return ok(self._page(rows, payload.get("start_cursor"), payload.get("page_size")))
        m = re.fullmatch(r"/v1/pages/([^/]+)", path)
        if method == "PATCH" and m:
            page = self.pages[m.group(1)]
            for k, v in payload["properties"].items():
                page["properties"][k].update(v)
            return ok(page)
        if path == "/v1/comments" and method == "GET":
            items = self.comments.get(q["block_id"], [])
            return ok(self._page(items, q.get("start_cursor"), int(q.get("page_size", 100))))
        if path == "/v1/comments" and method == "POST":
            pid = payload["parent"]["page_id"]
            rich = [dict(r, plain_text=r["text"]["content"]) for r in payload["rich_text"]]
            self.comments.setdefault(pid, []).append({"object": "comment", "rich_text": rich})
            return ok({"object": "comment"})
        raise AssertionError(f"unexpected request {method} {path}")

    def writes(self):
        return [(m, p, pl) for m, p, _, pl, _ in self.calls if m != "GET" and not p.endswith("/query")]


def source(fake=None, **kw):
    fake = fake or FakeNotion()
    return NotionSource(PARENT, token=TOKEN, transport=fake, clock=lambda: NOW, **kw), fake


class TokenFileTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = Path(self.dir.name) / "notion.token"

    def tearDown(self):
        self.dir.cleanup()

    def write(self, text, mode):
        self.path.write_text(text)
        os.chmod(self.path, mode)

    def assertRefuses(self, pattern):
        with self.assertRaises(TokenError) as cm:
            load_token(self.path)
        self.assertRegex(str(cm.exception), pattern)
        self.assertNotIn(TOKEN, str(cm.exception))
        self.assertNotIn("SECRET", str(cm.exception))

    def test_reads_a_0600_file_and_strips_it(self):
        self.write(f"  {TOKEN}\n", 0o600)
        self.assertEqual(load_token(self.path), TOKEN)

    def test_a_0400_file_is_fine(self):
        self.write(TOKEN, 0o400)
        self.assertEqual(load_token(self.path), TOKEN)

    def test_refuses_a_missing_file(self):
        self.assertRefuses("no Notion token file")

    def test_refuses_an_empty_file(self):
        self.write(" \n", 0o600)
        self.assertRefuses("empty")

    def test_refuses_0644(self):
        self.write(TOKEN, 0o644)
        self.assertRefuses("0644")

    def test_refuses_group_or_other_write_or_exec(self):
        for mode in (0o620, 0o602, 0o640, 0o700, 0o660):
            with self.subTest(mode=oct(mode)):
                self.write(TOKEN, mode)
                self.assertRefuses("must be 0600")

    def test_refuses_a_symlink(self):
        real = Path(self.dir.name) / "real"
        real.write_text(TOKEN)
        os.chmod(real, 0o600)
        self.path.symlink_to(real)
        self.assertRefuses("can't open")

    def test_never_falls_back_to_the_environment(self):
        with mock.patch.dict(os.environ, {"NOTION_TOKEN": TOKEN, "NOTION_API_KEY": TOKEN}):
            self.assertRefuses("no Notion token file")

    def test_default_path_ignores_HOME(self):
        with mock.patch.dict(os.environ, {"HOME": self.dir.name}):
            self.assertNotEqual(notion.token_path().parent.parent.parent, Path(self.dir.name))
        self.assertEqual(notion.token_path().parts[-3:], (".config", "productswarm", "notion.token"))

    def test_constructor_loads_the_token_when_none_is_given(self):
        self.write(TOKEN, 0o600)
        fake = FakeNotion()
        with mock.patch.object(notion, "token_path", return_value=self.path):
            src = NotionSource(PARENT, transport=fake)
        src.adopt()
        self.assertEqual(fake.calls[0][4]["Authorization"], f"Bearer {TOKEN}")

    def test_constructor_refuses_without_a_file(self):
        with mock.patch.object(notion, "token_path", return_value=self.path), \
                mock.patch.dict(os.environ, {"NOTION_TOKEN": TOKEN}):
            with self.assertRaises(TokenError):
                NotionSource(PARENT, transport=FakeNotion())

    def test_module_never_reads_or_writes_the_environment(self):
        tree = ast.parse(Path(notion.__file__).read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                self.assertNotIn(node.attr, {"environ", "environb", "getenv", "putenv"})
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                mods = [a.name for a in node.names] + [getattr(node, "module", None) or ""]
                for mod in mods:
                    self.assertNotIn(mod.split(".")[0], {"subprocess", "logging"})
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                self.assertNotIn(node.func.id, {"print", "getenv"})


class ProtocolTest(unittest.TestCase):
    def test_satisfies_specsource(self):
        src, _ = source()
        self.assertIsInstance(src, SpecSource)
        self.assertEqual(src.name, "notion")
        self.assertFalse(src.simulated)

    def test_pins_the_single_table_api_version(self):
        self.assertEqual(NOTION_VERSION, "2022-06-28")
        src, fake = source()
        src.adopt()
        self.assertTrue(all(c[4]["Notion-Version"] == NOTION_VERSION for c in fake.calls))

    def test_repr_hides_the_token(self):
        src, _ = source()
        self.assertNotIn(TOKEN, repr(src))
        self.assertNotIn(TOKEN, str(src))
        self.assertIn(PARENT, repr(src))


class AdoptTest(unittest.TestCase):
    def test_accepts_the_layout(self):
        src, fake = source()
        self.assertEqual(src.adopt(), {"initiatives": INIT_DB, "features": FEAT_DB})
        self.assertEqual(fake.writes(), [])

    def test_missing_database(self):
        fake = FakeNotion()
        fake.parent_children = [b for b in fake.parent_children if b["id"] != FEAT_DB]
        with self.assertRaisesRegex(SchemaError, "one 'Features' database.*found 0"):
            source(fake)[0].adopt()

    def test_doubled_database(self):
        fake = FakeNotion()
        fake.parent_children.append(dict(fake.parent_children[1], id="dup"))
        with self.assertRaisesRegex(SchemaError, "found 2"):
            source(fake)[0].adopt()

    def test_missing_property(self):
        fake = FakeNotion()
        del fake.databases[FEAT_DB]["properties"]["Last synced"]
        with self.assertRaisesRegex(SchemaError, "no 'Last synced' property"):
            source(fake)[0].adopt()

    def test_wrong_property_type(self):
        fake = FakeNotion()
        fake.databases[FEAT_DB]["properties"]["PR"] = {"type": "rich_text", "rich_text": {}}
        with self.assertRaisesRegex(SchemaError, "Features.PR is rich_text, expected url"):
            source(fake)[0].adopt()

    def test_unknown_status(self):
        fake = FakeNotion()
        fake.databases[FEAT_DB]["properties"]["Status"]["status"]["options"].append(
            {"name": "Parked"})
        with self.assertRaisesRegex(SchemaError, "unknown status Parked"):
            source(fake)[0].adopt()

    def test_missing_status(self):
        fake = FakeNotion()
        opts = fake.databases[FEAT_DB]["properties"]["Status"]["status"]["options"]
        opts[:] = [o for o in opts if o["name"] != "Blocked"]
        with self.assertRaisesRegex(SchemaError, "lacks Blocked"):
            source(fake)[0].adopt()

    def test_initiative_statuses_checked(self):
        fake = FakeNotion()
        fake.databases[INIT_DB]["properties"]["Status"]["status"]["options"].pop()
        with self.assertRaisesRegex(SchemaError, "Initiatives.Status lacks Done"):
            source(fake)[0].adopt()

    def test_relation_must_point_at_initiatives(self):
        fake = FakeNotion()
        fake.databases[FEAT_DB]["properties"]["Initiative"]["relation"]["database_id"] = "x" * 32
        with self.assertRaisesRegex(SchemaError, "does not relate"):
            source(fake)[0].adopt()

    def test_id_prefix(self):
        fake = FakeNotion()
        fake.databases[FEAT_DB]["properties"]["ID"]["unique_id"]["prefix"] = "F"
        with self.assertRaisesRegex(SchemaError, "prefix"):
            source(fake)[0].adopt()

    def test_reads_every_page_of_children(self):
        fake = FakeNotion()
        fake.page_size = 1
        self.assertEqual(source(fake)[0].adopt()["features"], FEAT_DB)


class ReadTest(unittest.TestCase):
    def test_list_features_of_one_initiative(self):
        src, _ = source()
        features = src.list_features(INITIATIVE)
        self.assertEqual([f.id for f in features], ["FEAT-1", "FEAT-2"])
        f = features[0]
        self.assertEqual((f.name, f.status, f.initiative_id), (
            "Effort mix chart", FeatureStatus.READY, INITIATIVE))
        self.assertEqual(f.last_edited, "2026-11-12T20:00:00.000Z")
        self.assertIsNone(f.issue_url)

    def test_list_features_paginates(self):
        fake = FakeNotion()
        fake.page_size = 1
        self.assertEqual(len(source(fake)[0].list_features(INITIATIVE)), 2)

    def test_unknown_status_on_a_row(self):
        fake = FakeNotion()
        fake.pages[PAGE1]["properties"]["Status"]["status"]["name"] = "Parked"
        with self.assertRaisesRegex(SchemaError, "FEAT-1 has unknown status 'Parked'"):
            source(fake)[0].list_features(INITIATIVE)

    def test_spec_parses_by_headings(self):
        src, _ = source()
        spec = src.get_spec("FEAT-1")
        self.assertIsInstance(spec, Spec)
        self.assertEqual(spec.problem, "Owners can't see specs ship.")
        self.assertEqual(spec.scope, "- Pull Ready features\n  - one issue each")
        self.assertEqual(spec.out_of_scope, "Writing spec bodies.")
        self.assertEqual(spec.acceptance_criteria, (
            Criterion("Pull opens one issue per Ready feature", False),
            Criterion("Push writes status back", True)))
        self.assertEqual(spec.notes, "See #937.")
        self.assertEqual(spec.pullable(), (True, None))

    def test_no_acceptance_criteria_is_not_pullable(self):
        spec = source()[0].get_spec("FEAT-2")
        self.assertIsNone(spec.acceptance_criteria)
        self.assertFalse(spec.pullable()[0])

    def test_bullets_are_not_criteria(self):
        fake = FakeNotion()
        fake.bodies[PAGE2].extend([block("heading_2", "Acceptance criteria"),
                                   block("bulleted_list_item", "looks like one")])
        spec = source(fake)[0].get_spec("FEAT-2")
        self.assertEqual(spec.acceptance_criteria, ())
        self.assertFalse(spec.pullable()[0])

    def test_toggle_heading_children(self):
        fake = FakeNotion()
        fake.bodies[PAGE2] = [block("heading_2", "Acceptance criteria", children=[
            block("to_do", "Inside a toggle", checked=False)])]
        spec = source(fake)[0].get_spec("FEAT-2")
        self.assertEqual(spec.acceptance_criteria, (Criterion("Inside a toggle"),))

    def test_unknown_heading(self):
        fake = FakeNotion()
        fake.bodies[PAGE2].append(block("heading_2", "Design"))
        with self.assertRaisesRegex(SchemaError, "unknown spec heading"):
            source(fake)[0].get_spec("FEAT-2")

    def test_repeated_heading(self):
        fake = FakeNotion()
        fake.bodies[PAGE2].append(block("heading_3", "Problem"))
        with self.assertRaisesRegex(SchemaError, "appears twice"):
            source(fake)[0].get_spec("FEAT-2")

    def test_unknown_feature(self):
        with self.assertRaisesRegex(SchemaError, "FEAT-9, found 0"):
            source()[0].get_spec("FEAT-9")
        with self.assertRaises(ValueError):
            source()[0].get_spec("not-a-feature")


class WriteTest(unittest.TestCase):
    def test_set_status_writes_properties_only(self):
        src, fake = source()
        src.set_status("FEAT-1", FeatureStatus.IN_PROGRESS)
        (method, path, payload), = fake.writes()
        self.assertEqual((method, path), ("PATCH", f"/v1/pages/{PAGE1}"))
        self.assertEqual(payload, {"properties": {
            "Status": {"status": {"name": "In progress"}},
            "Last synced": {"date": {"start": NOW}}}})

    def test_set_status_refuses_draft_and_ready_before_any_request(self):
        for status in (FeatureStatus.DRAFT, FeatureStatus.READY, "Ready"):
            with self.subTest(status=status):
                src, fake = source()
                with self.assertRaises(ValueError):
                    src.set_status("FEAT-1", status)
                self.assertEqual(fake.calls, [])

    def test_blocked_reason_is_one_marked_comment(self):
        src, fake = source()
        src.set_status("FEAT-1", FeatureStatus.BLOCKED, reason="issue closed unmerged")
        src.set_status("FEAT-1", FeatureStatus.BLOCKED, reason="issue  closed unmerged")
        self.assertEqual(len(fake.comments[PAGE1]), 1)
        self.assertIn("Blocked: issue closed unmerged",
                      notion._plain(fake.comments[PAGE1][0]["rich_text"]))

    def test_set_links(self):
        src, fake = source()
        src.set_links("FEAT-1", pr_url="https://github.com/o/r/pull/7")
        (_, _, payload), = fake.writes()
        self.assertEqual(set(payload["properties"]), {"PR", "Last synced"})
        self.assertEqual(fake.pages[PAGE1]["properties"]["PR"]["url"],
                         "https://github.com/o/r/pull/7")
        src.set_links("FEAT-1")
        self.assertEqual(len(fake.writes()), 1)

    def test_comment_writes_once_per_marker(self):
        src, fake = source()
        self.assertTrue(src.comment("FEAT-1", "Shipped in #7.\n\n-- lead (m)", "swarm:pr=7"))
        self.assertFalse(src.comment("FEAT-1", "Shipped again", "swarm:pr=7"))
        self.assertEqual(len(fake.comments[PAGE1]), 1)
        # swarm:pr=7 is not swarm:pr=71
        self.assertTrue(src.comment("FEAT-1", "Another", "swarm:pr=71"))
        self.assertEqual(len(fake.comments[PAGE1]), 2)

    def test_comment_reads_every_page_of_comments(self):
        fake = FakeNotion()
        fake.page_size = 1
        src, _ = source(fake)
        src.comment("FEAT-1", "a", "swarm:pr=1")
        src.comment("FEAT-1", "b", "swarm:pr=2")
        self.assertFalse(src.comment("FEAT-1", "a", "swarm:pr=1"))
        self.assertEqual(len(fake.comments[PAGE1]), 2)

    def test_long_comment_is_split_into_segments(self):
        src, fake = source()
        src.comment("FEAT-1", "x" * 4500, "swarm:pr=3")
        (_, _, payload), = fake.writes()
        self.assertTrue(all(len(r["text"]["content"]) <= 2000 for r in payload["rich_text"]))


class ScopeTest(unittest.TestCase):
    """No request the backend makes creates a page or database, reads users, or writes a
    page body; and the scope guard refuses those calls if code ever tries them."""

    ALLOWED = {
        ("GET", "children"), ("GET", "database"), ("POST", "query"),
        ("PATCH", "page"), ("GET", "comments"), ("POST", "comments"),
    }

    def classify(self, method, path):
        if re.fullmatch(r"/v1/blocks/[^/]+/children", path):
            return method, "children"
        if re.fullmatch(r"/v1/databases/[^/]+/query", path):
            return method, "query"
        if re.fullmatch(r"/v1/databases/[^/]+", path):
            return method, "database"
        if re.fullmatch(r"/v1/pages/[^/]+", path):
            return method, "page"
        if path == "/v1/comments":
            return method, "comments"
        return method, path

    def test_a_full_run_makes_only_allowed_calls(self):
        src, fake = source()
        src.adopt()
        for f in src.list_features(INITIATIVE):
            src.get_spec(f.id)
        src.set_status("FEAT-1", FeatureStatus.IN_REVIEW)
        src.set_links("FEAT-1", issue_url="https://github.com/o/r/issues/1",
                      pr_url="https://github.com/o/r/pull/2")
        src.set_status("FEAT-1", FeatureStatus.BLOCKED, reason="held")
        src.comment("FEAT-1", "Shipped", "swarm:pr=2")
        for method, path, _, payload, _ in fake.calls:
            kind = self.classify(method, path)
            self.assertIn(kind, self.ALLOWED, (method, path))
            self.assertFalse(path.startswith("/v1/users"))
            if kind == ("PATCH", "page"):
                self.assertEqual(set(payload), {"properties"})
                self.assertLessEqual(set(payload["properties"]), notion.BRIDGE_PROPS)
            if kind == ("POST", "comments"):
                self.assertEqual(set(payload["parent"]), {"page_id"})

    def test_guard_refuses_out_of_scope_calls(self):
        src, fake = source()
        bad = [
            ("POST", "/v1/pages", {"parent": {"database_id": FEAT_DB}, "properties": {}}),
            ("POST", "/v1/databases", {"parent": {"page_id": PARENT}}),
            ("PATCH", f"/v1/databases/{FEAT_DB}", {"properties": {}}),
            ("GET", "/v1/users", None),
            ("GET", "/v1/users/me", None),
            ("PATCH", f"/v1/blocks/{PAGE1}/children", {"children": []}),
            ("PATCH", f"/v1/blocks/{PAGE1}", {"paragraph": {}}),
            ("DELETE", f"/v1/blocks/{PAGE1}", None),
            ("PATCH", f"/v1/pages/{PAGE1}", {"archived": True}),
            ("PATCH", f"/v1/pages/{PAGE1}", {"properties": {}, "archived": True}),
            ("PATCH", f"/v1/pages/{PAGE1}", {"properties": {"Name": {"title": []}}}),
            ("POST", "/v1/comments", {"discussion_id": "d", "rich_text": []}),
            ("POST", "/v1/search", {}),
        ]
        for method, path, payload in bad:
            with self.subTest(method=method, path=path):
                with self.assertRaises(ScopeError):
                    src._request(method, path, payload)
        self.assertEqual(fake.calls, [])


class SecrecyTest(unittest.TestCase):
    def test_http_errors_never_carry_the_token(self):
        def echo(method, url, headers, body):
            # A hostile or buggy response that echoes the auth header back.
            return 401, json.dumps({"code": "unauthorized",
                                    "message": f"bad {headers['Authorization']}"}).encode()
        src = NotionSource(PARENT, token=TOKEN, transport=echo)
        with self.assertRaises(NotionError) as cm:
            src.adopt()
        self.assertNotIn(TOKEN, str(cm.exception))
        self.assertIn("401 unauthorized", str(cm.exception))

    def test_network_errors_never_carry_the_token(self):
        def down(method, url, headers, body):
            raise notion.NotionError("Notion request failed: ConnectionRefusedError")
        src = NotionSource(PARENT, token=TOKEN, transport=down)
        with self.assertRaises(NotionError) as cm:
            src.list_features(INITIATIVE)
        self.assertNotIn(TOKEN, str(cm.exception))

    def test_schema_and_scope_errors_never_carry_the_token(self):
        fake = FakeNotion()
        del fake.databases[FEAT_DB]["properties"]["ID"]
        src, _ = source(fake)
        for call in (src.adopt, lambda: src._request("GET", "/v1/users"),
                     lambda: src.set_status("FEAT-1", "Draft")):
            with self.subTest(call=call):
                with self.assertRaises(Exception) as cm:
                    call()
                self.assertNotIn(TOKEN, str(cm.exception))
                self.assertNotIn(TOKEN, repr(cm.exception))


if __name__ == "__main__":
    unittest.main()
