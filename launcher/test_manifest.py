"""Tests for launcher/manifest.py.

Run: python3 -m unittest discover -s launcher
"""
import io
import sys
import tempfile
import unittest
import unittest.mock
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
        # #487: every role in swarm.toml has a prompt, without pinning the list of roles.
        sessions = m.load()
        self.assertTrue(sessions)
        for role in {s.role for s in sessions}:
            self.assertTrue((m.ROOT / "roles" / f"{role}.md").is_file(), role)

    def test_repo_manifest_runs_a_reviewer_by_default(self):   # L6, #51
        self.assertGreaterEqual(sum(s.role == "reviewer" for s in m.load()), 1)

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


class LoadValidTest(Base):
    """load_all() / parse_valid() (#487): skip a bad [[session]] entry, keep the rest."""
    WATCH = "[watch]\ninterval_minutes = 5\nmax_live = 2\nmax_turns = 200\n"

    def valid(self, text):
        return m.parse_valid(text, Path("swarm.toml"), self.roles)

    def test_bad_entry_beside_good_ones(self):
        text = self.WATCH + session("builder", 2) + session("ghost") + session("docs", count=0) \
            + session("reviewer") + session("builder")
        sessions, limits, problems = self.valid(text)
        self.assertEqual([s.name for s in sessions], ["builder-1", "builder-2", "reviewer-1"])
        self.assertEqual(limits.max_live, 2)
        self.assertEqual(problems, [
            "session 2 (ghost): unknown role 'ghost' (no roles/ghost.md)",
            "session 3 (docs): count must be at least 1, got 0",
            "session 5 (builder): role 'builder' already listed in session 1; use count instead"])
        with self.assertRaises(m.ManifestError) as cm:   # load() and parse_all() stay strict
            self.parse(text)
        self.assertEqual(cm.exception.problems, problems)

    def test_good_manifest_has_no_problems(self):
        self.assertEqual(self.valid(session())[2], [])

    def test_bad_watch_table_raises(self):
        text = "[watch]\ninterval_minutes = 5\nmax_live = 0\n" + session() + session("ghost")
        with self.assertRaises(m.ManifestError) as cm:
            self.valid(text)
        self.assertEqual(cm.exception.problems, [
            "watch: max_live must be a whole number of at least 1, got 0",
            "session 2 (ghost): unknown role 'ghost' (no roles/ghost.md)"])

    def test_bad_toml_raises(self):
        with self.assertRaises(m.ManifestError):
            self.valid("[[session]\n")

    def test_load_all_and_load_watch_read_past_a_bad_entry(self):
        path = self.dir / "swarm.toml"
        path.write_text(self.WATCH + session("ghost") + session("docs"))
        sessions, limits, problems = m.load_all(path, self.roles)
        self.assertEqual([s.name for s in sessions], ["docs-1"])
        self.assertEqual(problems, ["session 1 (ghost): unknown role 'ghost' (no roles/ghost.md)"])
        self.assertEqual(m.load_watch(path, self.roles).max_turns, 200)
        with self.assertRaises(m.ManifestError):
            m.load(path, self.roles)
        with self.assertRaises(m.ManifestError):
            m.load_all(self.dir / "nope.toml", self.roles)


class ReviewInActionsTest(Base):
    """[watch] review_in_actions (#216, GOV-0019): optional, default false, true or false only."""
    WATCH = "[watch]\ninterval_minutes = 5\nmax_live = 2\nmax_turns = 200\n"

    def limits(self, extra=""):
        return m.parse_all(self.WATCH + extra + session(), Path("swarm.toml"), self.roles)[1]

    def test_missing_is_false(self):
        self.assertIs(self.limits().review_in_actions, False)

    def test_true_and_false(self):
        self.assertIs(self.limits("review_in_actions = true\n").review_in_actions, True)
        self.assertIs(self.limits("review_in_actions = false\n").review_in_actions, False)

    def test_wrong_type(self):
        for bad in ('"true"', "1", "0", "1.0", "[]"):
            with self.subTest(value=bad):
                with self.assertRaises(m.ManifestError) as cm:
                    self.limits(f"review_in_actions = {bad}\n")
                self.assertEqual(len(cm.exception.problems), 1)
                self.assertIn("watch: review_in_actions must be true or false",
                              cm.exception.problems[0])

    def test_cli_shows_it(self):
        path = self.dir / "swarm.toml"
        for value, shown in (("true", "[review] left to Actions"), ("false", "[review] local")):
            path.write_text(self.WATCH + f"review_in_actions = {value}\n" + session())
            out = io.StringIO()
            with redirect_stdout(out), unittest.mock.patch.object(m, "ROOT", self.dir):
                self.assertEqual(m.main(["manifest.py", str(path)]), 0)
            self.assertIn(f"\t{shown}\t", out.getvalue().splitlines()[-1])

    def test_repo_manifest_parses_it(self):
        # The owner turns it on or off (#260), so check only that the repo's value parses (#285).
        self.assertIsInstance(m.load_watch().review_in_actions, bool)


class CallInsTest(Base):
    """[watch] call_ins (#520, GOV-0023): optional, default false, true or false only."""
    WATCH = "[watch]\ninterval_minutes = 5\nmax_live = 2\nmax_turns = 200\n"

    def limits(self, extra=""):
        return m.parse_all(self.WATCH + extra + session(), Path("swarm.toml"), self.roles)[1]

    def test_missing_is_false(self):
        self.assertIs(self.limits().call_ins, False)

    def test_true_and_false(self):
        self.assertIs(self.limits("call_ins = true\n").call_ins, True)
        self.assertIs(self.limits("call_ins = false\n").call_ins, False)

    def test_wrong_type(self):
        for bad in ('"true"', "1", "[]"):
            with self.subTest(value=bad):
                with self.assertRaises(m.ManifestError) as cm:
                    self.limits(f"call_ins = {bad}\n")
                self.assertEqual(len(cm.exception.problems), 1)
                self.assertIn("watch: call_ins must be true or false", cm.exception.problems[0])

    def test_cli_shows_it(self):
        path = self.dir / "swarm.toml"
        for value, shown in (("true", "call-ins on"), ("false", "call-ins off")):
            path.write_text(self.WATCH + f"call_ins = {value}\n" + session())
            out = io.StringIO()
            with redirect_stdout(out), unittest.mock.patch.object(m, "ROOT", self.dir):
                self.assertEqual(m.main(["manifest.py", str(path)]), 0)
            self.assertIn(shown, out.getvalue().splitlines()[-1].split("\t"))


class DailyTest(Base):
    """[watch] daily, daily_at, report_issue (#588, GOV-0029): off by default; daily = true
    needs the other two."""
    WATCH = "[watch]\ninterval_minutes = 5\nmax_live = 2\nmax_turns = 200\n"
    ON = 'daily = true\ndaily_at = "08:30"\nreport_issue = 600\n'

    def limits(self, extra=""):
        return m.parse_all(self.WATCH + extra + session(), Path("swarm.toml"), self.roles)[1]

    def problems(self, extra):
        with self.assertRaises(m.ManifestError) as cm:
            self.limits(extra)
        return cm.exception.problems

    def test_off_by_default(self):
        limits = self.limits()
        self.assertIs(limits.daily, False)
        self.assertIsNone(limits.daily_at)
        self.assertIsNone(limits.report_issue)

    def test_on(self):
        limits = self.limits(self.ON)
        self.assertIs(limits.daily, True)
        self.assertEqual(limits.daily_at, m.dt.time(8, 30))
        self.assertEqual(limits.report_issue, 600)

    def test_on_without_report_issue_errors(self):
        self.assertEqual(self.problems('daily = true\ndaily_at = "08:30"\n'),
                         ["watch: daily = true needs 'report_issue'"])

    def test_on_without_daily_at_errors(self):
        self.assertEqual(self.problems("daily = true\nreport_issue = 600\n"),
                         ["watch: daily = true needs 'daily_at'"])

    def test_on_alone_names_both(self):
        self.assertEqual(len(self.problems("daily = true\n")), 2)

    def test_settings_allowed_while_off(self):
        limits = self.limits('daily = false\ndaily_at = "08:30"\nreport_issue = 600\n')
        self.assertIs(limits.daily, False)
        self.assertEqual(limits.report_issue, 600)

    def test_bad_values(self):
        for extra, said in (('daily = "yes"\n', "daily must be true or false"),
                            ('daily_at = "8:30"\n', "daily_at must be a local time"),
                            ('daily_at = "24:00"\n', "daily_at must be a local time"),
                            ("daily_at = 830\n", "daily_at must be a local time"),
                            ("report_issue = 0\n", "report_issue must be an issue number"),
                            ('report_issue = "600"\n', "report_issue must be an issue number"),
                            ("report_issue = true\n", "report_issue must be an issue number")):
            with self.subTest(extra=extra):
                problems = self.problems(extra)
                self.assertEqual(len(problems), 1)
                self.assertIn(said, problems[0])

    def test_cli_shows_it(self):
        path = self.dir / "swarm.toml"
        for extra, shown in ((self.ON, "[daily] on #600 at 08:30"), ("", "[daily] off")):
            path.write_text(self.WATCH + extra + session())
            out = io.StringIO()
            with redirect_stdout(out), unittest.mock.patch.object(m, "ROOT", self.dir):
                self.assertEqual(m.main(["manifest.py", str(path)]), 0)
            self.assertIn(shown, out.getvalue().splitlines()[-1].split("\t"))

    def test_repo_manifest_leaves_it_off(self):
        self.assertIs(m.load_watch(m.DEFAULT_PATH).daily, False)


class AsksTest(Base):
    """[watch] asks (#590, GOV-0029): off by default; asks = true needs report_issue."""
    WATCH = "[watch]\ninterval_minutes = 5\nmax_live = 2\nmax_turns = 200\n"

    def limits(self, extra=""):
        return m.parse_all(self.WATCH + extra + session(), Path("swarm.toml"), self.roles)[1]

    def problems(self, extra):
        with self.assertRaises(m.ManifestError) as cm:
            self.limits(extra)
        return cm.exception.problems

    def test_off_by_default(self):
        self.assertIs(self.limits().asks, False)

    def test_on_with_the_report_issue(self):
        limits = self.limits("asks = true\nreport_issue = 600\n")
        self.assertIs(limits.asks, True)
        self.assertEqual(limits.report_issue, 600)
        self.assertIs(limits.daily, False)          # it doesn't need [daily]

    def test_on_without_report_issue_errors(self):
        self.assertEqual(self.problems("asks = true\n"), ["watch: asks = true needs 'report_issue'"])

    def test_must_be_true_or_false(self):
        self.assertEqual(self.problems('asks = "yes"\nreport_issue = 600\n'),
                         ["watch: asks must be true or false, got 'yes'"])

    def test_cli_shows_it(self):
        path = self.dir / "swarm.toml"
        for extra, shown in (("asks = true\nreport_issue = 600\n", "[ask] on #600"), ("", "[ask] off")):
            path.write_text(self.WATCH + extra + session())
            out = io.StringIO()
            with redirect_stdout(out), unittest.mock.patch.object(m, "ROOT", self.dir):
                self.assertEqual(m.main(["manifest.py", str(path)]), 0)
            self.assertIn(shown, out.getvalue().splitlines()[-1].split("\t"))

    def test_repo_manifest_leaves_it_off(self):
        self.assertIs(m.load_watch(m.DEFAULT_PATH).asks, False)


class ActionsMaxReviewsTest(Base):
    """[watch] actions_max_reviews (#257): optional, a whole number of at least 1."""
    WATCH = "[watch]\ninterval_minutes = 5\nmax_live = 2\nmax_turns = 200\n"

    def limits(self, extra=""):
        return m.parse_all(self.WATCH + extra + session(), Path("swarm.toml"), self.roles)[1]

    def test_missing_is_none(self):
        self.assertIsNone(self.limits().actions_max_reviews)

    def test_valid(self):
        for v in (1, 2, 10):
            self.assertEqual(self.limits(f"actions_max_reviews = {v}\n").actions_max_reviews, v)

    def test_wrong_type(self):
        for bad in ('"2"', "2.0", "true", "[]"):
            with self.subTest(value=bad):
                with self.assertRaises(m.ManifestError) as cm:
                    self.limits(f"actions_max_reviews = {bad}\n")
                self.assertEqual(len(cm.exception.problems), 1)
                self.assertIn("watch: actions_max_reviews must be a whole number of at least 1",
                              cm.exception.problems[0])

    def test_below_one(self):
        for bad in ("0", "-1"):
            with self.subTest(value=bad):
                with self.assertRaises(m.ManifestError) as cm:
                    self.limits(f"actions_max_reviews = {bad}\n")
                self.assertIn("at least 1, got", cm.exception.problems[0])

    def test_cli_shows_it(self):
        path = self.dir / "swarm.toml"
        for extra, shown in (("actions_max_reviews = 2\n", "at most 2 Actions reviews a sweep"),
                             ("", "no actions_max_reviews")):
            path.write_text(self.WATCH + extra + session())
            out = io.StringIO()
            with redirect_stdout(out), unittest.mock.patch.object(m, "ROOT", self.dir):
                self.assertEqual(m.main(["manifest.py", str(path)]), 0)
            self.assertIn(shown, out.getvalue().splitlines()[-1].split("\t"))


if __name__ == "__main__":
    unittest.main()
