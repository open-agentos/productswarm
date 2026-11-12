"""Tests for launcher/specs/config.py (#952): the [specs] table and the backend it picks.

Run: python3 run_tests.py launcher
"""
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from specs import config  # noqa: E402
from specs.config import SpecsConfig, SpecsConfigError  # noqa: E402
from specs.fake import FakeSource  # noqa: E402

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

    def test_notion_and_productboard_are_not_built_yet(self):
        for backend in ("notion", "productboard"):
            with self.assertRaises(SpecsConfigError) as cm:
                config.source(SpecsConfig(backend, parent_page="abc123"))
            self.assertIn("not built yet", str(cm.exception), backend)


if __name__ == "__main__":
    unittest.main()
