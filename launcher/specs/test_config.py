"""Tests for launcher/specs/config.py (#952): the [specs] table and the backend it picks.

Run: python3 run_tests.py launcher
"""
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from specs import config  # noqa: E402
from specs.config import SpecsConfig, SpecsConfigError  # noqa: E402
from specs import notion  # noqa: E402
from specs.fake import FakeSource  # noqa: E402
from specs.notion import NotionSource  # noqa: E402

FIXTURE = Path(__file__).resolve().parent / "testdata" / "fake_initiative.json"
SESSION = '[[session]]\nrole = "builder"\ncount = 1\nmodel = "claude-opus-5-5"\n'


class LoadTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def write(self, text: str) -> Path:
        p = self.dir / "swarm.toml"
        p.write_text(SESSION + text, encoding="utf-8")
        return p

    def error(self, text: str) -> str:
        with self.assertRaises(SpecsConfigError) as cm:
            config.load(self.write(text))
        return str(cm.exception)

    def test_no_table_is_none(self):
        self.assertIsNone(config.load(self.write("")))

    def test_reads_every_key(self):
        cfg = config.load(self.write('[specs]\nbackend = "notion"\nparent_page = "abc123"\n'
                                     'fixture = "specs/f.json"\n'))
        self.assertEqual(cfg, SpecsConfig("notion", "abc123", self.dir / "specs" / "f.json"))

    def test_relative_fixture_is_beside_the_manifest_and_absolute_is_kept(self):
        cfg = config.load(self.write('[specs]\nbackend = "fake"\nfixture = "f.json"\n'))
        self.assertEqual(cfg.fixture, self.dir / "f.json")
        cfg = config.load(self.write(f'[specs]\nbackend = "fake"\nfixture = "{FIXTURE}"\n'))
        self.assertEqual(cfg.fixture, FIXTURE)

    def test_unknown_key_is_named(self):
        self.assertIn("unknown key 'token'",
                      self.error('[specs]\nbackend = "notion"\ntoken = "secret"\n'))

    def test_unknown_backend_is_named(self):
        self.assertIn("unknown backend 'jira'", self.error('[specs]\nbackend = "jira"\n'))

    def test_backend_is_required(self):
        self.assertIn("missing 'backend'", self.error('[specs]\nfixture = "f.json"\n'))

    def test_values_must_be_non_empty_strings(self):
        self.assertIn("parent_page must be a non-empty string",
                      self.error('[specs]\nbackend = "notion"\nparent_page = 7\n'))
        self.assertIn("fixture must be a non-empty string",
                      self.error('[specs]\nbackend = "fake"\nfixture = ""\n'))

    def test_specs_not_a_table(self):
        p = self.dir / "swarm.toml"
        p.write_text('specs = "fake"\n' + SESSION, encoding="utf-8")
        with self.assertRaises(SpecsConfigError) as cm:
            config.load(p)
        self.assertIn("must be a [specs] table", str(cm.exception))

    def test_missing_file_and_bad_toml(self):
        with self.assertRaises(SpecsConfigError):
            config.load(self.dir / "nope.toml")
        self.assertIn("not valid TOML", self.error("[specs\n"))


class SourceTest(unittest.TestCase):
    def test_fake_returns_a_fake_source(self):
        with tempfile.TemporaryDirectory() as d:
            shutil.copy(FIXTURE, Path(d) / "fixture.json")
            p = Path(d) / "swarm.toml"
            p.write_text(SESSION + '[specs]\nbackend = "fake"\nfixture = "fixture.json"\n',
                         encoding="utf-8")
            src = config.source(config.load(p))
        self.assertIsInstance(src, FakeSource)
        self.assertEqual(src.path, Path(d) / "fixture.json")

    def test_fake_needs_a_fixture(self):
        with self.assertRaises(SpecsConfigError) as cm:
            config.source(SpecsConfig("fake"))
        self.assertIn("needs 'fixture'", str(cm.exception))

    def test_productboard_is_not_built_yet(self):
        with self.assertRaises(SpecsConfigError) as cm:
            config.source(SpecsConfig("productboard", parent_page="abc123"))
        self.assertIn("not built yet", str(cm.exception))


class NotionSourceTest(unittest.TestCase):
    """The notion backend (#1007): a temporary token file and a transport that fails the test
    if called, so no network and no real token."""
    TOKEN = "ntn_TESTtoken0123456789"
    PARENT = "416ec22e-b1e3-8129-8868-d1d23514d60e"

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.token = Path(tmp.name) / "notion.token"
        self.token.write_text(self.TOKEN + "\n", encoding="utf-8")
        os.chmod(self.token, 0o600)
        self.requests = []
        for target, new in (("token_path", lambda: self.token),
                            ("urllib_transport", lambda *a: self.requests.append(a))):
            p = mock.patch.object(notion, target, new)
            p.start()
            self.addCleanup(p.stop)

    def error(self, cfg) -> str:
        with self.assertRaises(SpecsConfigError) as cm:
            config.source(cfg)
        self.assertEqual(self.requests, [])
        return str(cm.exception)

    def test_builds_a_notion_source_and_makes_no_request(self):
        src = config.source(SpecsConfig("notion", parent_page=self.PARENT))
        self.assertIsInstance(src, NotionSource)
        self.assertEqual(src.parent_page, self.PARENT)
        self.assertEqual(self.requests, [])
        self.assertNotIn(self.TOKEN, repr(src))

    def test_needs_a_parent_page(self):
        self.assertIn("backend \"notion\" needs 'parent_page'", self.error(SpecsConfig("notion")))

    def test_missing_token_is_one_line(self):
        self.token.unlink()
        msg = self.error(SpecsConfig("notion", parent_page=self.PARENT))
        self.assertIn(f"no Notion token file at {self.token}", msg)
        self.assertNotIn("\n", msg)

    def test_token_not_0600_is_one_line_without_the_token(self):
        os.chmod(self.token, 0o644)
        msg = self.error(SpecsConfig("notion", parent_page=self.PARENT))
        self.assertIn("has mode 0644; it must be 0600", msg)
        self.assertNotIn("\n", msg)
        self.assertNotIn(self.TOKEN, msg)

    def test_the_repo_manifest_names_notion(self):
        cfg = config.load(Path(__file__).resolve().parents[2] / "swarm.toml")
        self.assertEqual((cfg.backend, cfg.parent_page, cfg.fixture),
                         ("notion", self.PARENT, None))

if __name__ == "__main__":
    unittest.main()
