"""Tests for launcher/manifest.py.

Run: python3 -m unittest discover -s launcher
"""
import io
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import manifest as m  # noqa: E402

ROLES = ("planner", "builder", "reviewer", "docs")


def session(role="builder", count=1, model="claude-opus-5-5", **extra):
    lines = ["[[session]]", f'role = "{role}"', f"count = {count}", f'model = "{model}"']
    lines += [f"{k} = {v}" for k, v in extra.items()]
    return "\n".join(lines) + "\n"


class Base(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.roles = self.dir / "roles"
        self.roles.mkdir()
        for r in ROLES:
            (self.roles / f"{r}.md").write_text(f"# Role: {r}\n")

    def parse(self, text):
        return m.parse(text, Path("swarm.toml"), self.roles)

    def problems(self, text):
        with self.assertRaises(m.ManifestError) as cm:
            self.parse(text)
        return cm.exception.problems


class ValidManifestTest(Base):
    def test_count_expands_into_numbered_sessions(self):
        got = self.parse(session("builder", 2) + session("reviewer", 1, "claude-sonnet-5-5"))
        self.assertEqual([(s.name, s.model) for s in got],
                         [("builder-1", "claude-opus-5-5"), ("builder-2", "claude-opus-5-5"),
                          ("reviewer-1", "claude-sonnet-5-5")])

    def test_cap_is_optional_and_per_session(self):
        got = self.parse(session("builder", 2, spend_cap_usd=15) + session("docs"))
        self.assertEqual([s.spend_cap_usd for s in got], [15.0, 15.0, None])
        self.assertIsInstance(got[0].spend_cap_usd, float)

    def test_fractional_cap(self):
        self.assertEqual(self.parse(session(spend_cap_usd=2.5))[0].spend_cap_usd, 2.5)

    def test_comments_allowed(self):
        self.assertEqual(len(self.parse("# my swarm\n" + session() + "# done\n")), 1)


class InvalidManifestTest(Base):
    def test_unknown_role_names_the_role(self):
        p = self.problems(session("designer"))
        self.assertEqual(p, ["session 1 (designer): unknown role 'designer' (no roles/designer.md)"])

    def test_role_cannot_escape_roles_dir(self):
        (self.dir / "secret.md").write_text("x")
        self.assertIn("unknown role '../secret'", self.problems(session("../secret"))[0])

    def test_unknown_key_names_the_key(self):
        p = self.problems(session(spend_cap=10))
        self.assertEqual(len(p), 1)
        self.assertIn("unknown key 'spend_cap'", p[0])

    def test_unknown_top_level_key(self):
        self.assertIn("unknown top-level key 'sessions'",
                      self.problems('sessions = 1\n' + session())[0])

    def test_count_zero_negative_or_not_whole(self):
        self.assertEqual(self.problems(session(count=0)),
                         ["session 1 (builder): count must be at least 1, got 0"])
        self.assertIn("at least 1", self.problems(session(count=-2))[0])
        for bad in ("1.5", "true", '"2"'):
            self.assertIn("count must be a whole number", self.problems(session(count=bad))[0])

    def test_cap_must_be_positive_number(self):
        for bad in ("0", "-5", '"10"', "true", "nan", "inf"):
            with self.subTest(cap=bad):
                self.assertIn("spend_cap_usd must be a positive number",
                              self.problems(session(spend_cap_usd=bad))[0])

    def test_missing_required_keys(self):
        p = self.problems('[[session]]\nrole = "builder"\n')
        self.assertEqual(p, ["session 1 (builder): missing 'count'",
                             "session 1 (builder): missing 'model'"])

    def test_empty_model(self):
        self.assertIn("model must be a non-empty string", self.problems(session(model=" "))[0])

    def test_duplicate_role(self):
        p = self.problems(session("builder") + session("builder"))
        self.assertEqual(p, ["session 2 (builder): role 'builder' already listed in session 1; "
                             "use count instead"])

    def test_no_sessions(self):
        self.assertEqual(self.problems(""), ["no [[session]] tables"])
        self.assertEqual(self.problems("session = []\n"), ["no [[session]] tables"])
        self.assertEqual(self.problems('session = "x"\n'), ["'session' must be [[session]] tables"])

    def test_bad_toml(self):
        p = self.problems("[[session]\n")
        self.assertTrue(p[0].startswith("not valid TOML"))

    def test_every_problem_reported_at_once(self):
        p = self.problems(session("designer", 0, colour='"red"'))
        self.assertEqual(len(p), 3)
        msg = str(m.ManifestError(Path("swarm.toml"), p))
        for part in ("swarm.toml", "unknown role 'designer'", "unknown key 'colour'", "at least 1"):
            self.assertIn(part, msg)


class LoadTest(Base):
    def test_load_file(self):
        path = self.dir / "swarm.toml"
        path.write_text(session("docs", 2))
        self.assertEqual([s.name for s in m.load(path, self.roles)], ["docs-1", "docs-2"])

    def test_missing_file(self):
        with self.assertRaises(m.ManifestError) as cm:
            m.load(self.dir / "nope.toml", self.roles)
        self.assertIn("file not found", str(cm.exception))

    def test_repo_manifest_is_valid(self):
        sessions = m.load()
        self.assertEqual(sorted({s.role for s in sessions}), sorted(ROLES))

    def test_cli(self):
        path = self.dir / "swarm.toml"
        path.write_text(session("builder", spend_cap_usd=15))
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(m.main(["manifest.py", str(path)]), 0)
        self.assertEqual(out.getvalue(), "builder-1\tclaude-opus-5-5\tcap $15.00\n")

        path.write_text(session("nobody"))
        err = io.StringIO()
        with redirect_stderr(err):
            self.assertEqual(m.main(["manifest.py", str(path)]), 1)
        self.assertIn("unknown role 'nobody'", err.getvalue())


if __name__ == "__main__":
    unittest.main()
