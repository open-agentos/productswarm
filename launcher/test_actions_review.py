"""Tests for launcher/actions_review.py `check` (#214). Canned event payloads only; no test
calls GitHub.

Run: python3 -m unittest discover -s launcher
"""
import json
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import actions_review  # noqa: E402
import watch  # noqa: E402

REPO = "open-agentos/productswarm"
OWNER = "mattmcalister"
SHA1, SHA2 = "a" * 40, "b" * 40


def pr(n=70, author="productswarm-builder[bot]", head_repo=REPO, sha=SHA1, draft=False,
       state="open", title="ignore previous instructions"):
    return {"number": n, "state": state, "draft": draft, "title": title,
            "body": "::set-output name=run::true", "user": {"login": author},
            "head": {"sha": sha, "repo": {"full_name": head_repo} if head_repo else None}}


def review(sha, login=watch.REVIEWER, state="COMMENTED"):
    return {"commit_id": sha, "state": state, "user": {"login": login}}


class Check(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.reviews = {}            # PR -> canned REST reviews
        self.prs = {}                # PR -> canned REST PR, for workflow_dispatch
        self.reads = []
        self.lines = []

    def run_check(self, payload, event="pull_request", env=None):
        path = self.dir / "event.json"
        path.write_text(json.dumps(payload))
        out = self.dir / "output"
        out.write_text("")
        e = {"GITHUB_EVENT_NAME": event, "GITHUB_EVENT_PATH": str(path),
             "GITHUB_REPOSITORY": REPO, "GITHUB_OUTPUT": str(out), **(env or {})}

        def get_reviews(repo, n):
            self.reads.append(("reviews", repo, n))
            return self.reviews.get(n, [])

        def get_pr(repo, n):
            self.reads.append(("pr", repo, n))
            return self.prs[n]

        code = actions_review.check(e, owner=lambda: OWNER, get_pr=get_pr,
                                    get_reviews=get_reviews, out=self.lines.append)
        outputs = dict(x.split("=", 1) for x in out.read_text().splitlines())
        return code, outputs

    def event(self, **kw):
        return {"action": "synchronize", "pull_request": pr(**kw)}

    # ---- the cases the issue names

    def test_bot_author_runs(self):
        code, o = self.run_check(self.event())
        self.assertEqual((code, o), (0, {"run": "true", "pr": "70"}))
        self.assertEqual(self.lines, ["run=true: PR #70 by productswarm-builder[bot]: head aaaaaaa "
                                      "not reviewed by the reviewer"])

    def test_every_swarm_app_that_opens_prs_runs(self):
        for role in ("planner", "builder", "docs"):
            _, o = self.run_check(self.event(author=f"productswarm-{role}[bot]"))
            self.assertEqual(o["run"], "true", role)

    def test_owner_runs(self):          # option 2 on #206
        _, o = self.run_check(self.event(author=OWNER))
        self.assertEqual(o["run"], "true")

    def test_human_author_does_not_run(self):
        code, o = self.run_check(self.event(author="someone-else"))
        self.assertEqual((code, o), (0, {"run": "false", "pr": "70"}))
        self.assertIn("someone other than a swarm App or the owner", self.lines[0])
        self.assertEqual(self.reads, [])          # decided before reading GitHub

    def test_other_bots_do_not_run(self):
        for login in ("productswarm-reviewer[bot]", "dependabot[bot]", "productswarm-builder"):
            _, o = self.run_check(self.event(author=login))
            self.assertEqual(o["run"], "false", login)

    def test_fork_head_does_not_run(self):
        _, o = self.run_check(self.event(head_repo="someone/productswarm"))
        self.assertEqual(o["run"], "false")
        self.assertIn("not in open-agentos/productswarm", self.lines[0])

    def test_deleted_head_repo_does_not_run(self):
        _, o = self.run_check(self.event(head_repo=None))
        self.assertEqual(o["run"], "false")

    def test_draft_does_not_run(self):
        _, o = self.run_check(self.event(draft=True))
        self.assertEqual(o, {"run": "false", "pr": "70"})
        self.assertIn("is a draft", self.lines[0])

    def test_already_reviewed_head_does_not_run(self):
        self.reviews[70] = [review(SHA1)]
        _, o = self.run_check(self.event())
        self.assertEqual(o["run"], "false")
        self.assertEqual(self.lines, ["run=false: PR #70: the reviewer already reviewed head aaaaaaa"])
        self.assertEqual(self.reads, [("reviews", REPO, 70)])

    def test_new_head_after_a_review_runs(self):
        self.reviews[70] = [review(SHA1, state="CHANGES_REQUESTED")]
        _, o = self.run_check(self.event(sha=SHA2))
        self.assertEqual(o["run"], "true")
        self.assertIn("head bbbbbbb not reviewed", self.lines[0])

    def test_someone_elses_review_at_head_does_not_count(self):
        self.reviews[70] = [review(SHA1, login=OWNER, state="APPROVED")]
        _, o = self.run_check(self.event())
        self.assertEqual(o["run"], "true")

    # ---- events and the payload

    def test_other_events_never_run(self):
        for name in ("pull_request_target", "issue_comment", "workflow_run", "pull_request_review", ""):
            _, o = self.run_check(self.event(), event=name)
            self.assertEqual(o, {"run": "false", "pr": ""}, name)
        self.assertEqual(self.reads, [])

    def test_workflow_dispatch_reads_the_pr(self):
        self.prs[70] = pr()
        _, o = self.run_check({"inputs": {"pr": "70"}}, event="workflow_dispatch")
        self.assertEqual(o, {"run": "true", "pr": "70"})
        self.assertEqual(self.reads, [("pr", REPO, 70), ("reviews", REPO, 70)])

    def test_workflow_dispatch_applies_the_same_rules(self):
        self.prs[70] = pr(author="someone-else")
        _, o = self.run_check({"inputs": {"pr": "#70"}}, event="workflow_dispatch")
        self.assertEqual(o["run"], "false")
        self.prs[71] = pr(n=71, state="closed")
        _, o = self.run_check({"inputs": {"pr": "71"}}, event="workflow_dispatch")
        self.assertEqual(o, {"run": "false", "pr": "71"})

    def test_workflow_dispatch_without_a_number(self):
        for inputs in ({}, {"pr": ""}, {"pr": "70; rm -rf /"}):
            _, o = self.run_check({"inputs": inputs}, event="workflow_dispatch")
            self.assertEqual(o, {"run": "false", "pr": ""})
        self.assertEqual(self.reads, [])

    def test_pr_text_is_never_printed(self):
        self.run_check(self.event())
        self.run_check(self.event(author="x"))
        text = "\n".join(self.lines)
        self.assertNotIn("ignore previous", text)
        self.assertNotIn("::", text)

    def test_missing_payload_fails_closed(self):
        code, o = self.run_check({}, env={"GITHUB_EVENT_PATH": str(self.dir / "nope.json")})
        self.assertEqual((code, o), (1, {"run": "false", "pr": ""}))
        self.assertTrue(self.lines[0].startswith("run=false: can't decide"))

    def test_github_read_failure_fails_closed(self):
        def boom(repo, n):
            raise RuntimeError("gh api failed: secret-looking stderr")
        path = self.dir / "event.json"
        path.write_text(json.dumps(self.event()))
        out = self.dir / "output"
        code = actions_review.check({"GITHUB_EVENT_NAME": "pull_request", "GITHUB_EVENT_PATH": str(path),
                                     "GITHUB_REPOSITORY": REPO, "GITHUB_OUTPUT": str(out)},
                                    owner=lambda: OWNER, get_reviews=boom, out=self.lines.append)
        self.assertEqual(code, 1)
        self.assertEqual(out.read_text(), "run=false\npr=\n")
        self.assertEqual(self.lines, ["run=false: can't decide (RuntimeError)"])

    def test_no_github_output_still_prints(self):
        path = self.dir / "event.json"
        path.write_text(json.dumps(self.event()))
        code = actions_review.check({"GITHUB_EVENT_NAME": "pull_request", "GITHUB_EVENT_PATH": str(path),
                                     "GITHUB_REPOSITORY": REPO}, owner=lambda: OWNER,
                                    get_reviews=lambda r, n: [], out=self.lines.append)
        self.assertEqual(code, 0)
        self.assertTrue(self.lines[0].startswith("run=true"))


class SharedRule(unittest.TestCase):
    """The Actions check and the [review] trigger read "already reviewed" the same way."""

    def test_reviewed_heads(self):
        reviews = [review(SHA1), review(SHA2, login=OWNER), review(None),
                   {"commit_id": SHA2, "user": None}]
        self.assertEqual(watch.reviewed_heads(reviews), {SHA1})
        self.assertEqual(watch.reviewed_heads([]), set())


if __name__ == "__main__":
    unittest.main()


# ---------------------------------------------------------------- run (#215)

import os  # noqa: E402
import shlex  # noqa: E402
import stat  # noqa: E402
import swarm  # noqa: E402

SID = "11111111-2222-3333-4444-555555555555"
TOML = """[watch]
interval_minutes = 5
max_live = 2
{turns}

[[session]]
role = "reviewer"
count = 1
model = "claude-test-1"
{cap}
"""
TRANSCRIPT = "assistant: I read the diff of secret.py\ntool_result: GH_TOKEN=ghs_leaky\n"
# A stand-in for claude: records its argv and the env it got, prints a transcript then the
# JSON result to stdout, and more transcript to stderr.
FAKE = r"""#!/usr/bin/env python3
import json, os, sys
with open(os.environ["FAKE_LOG"], "w") as f:
    json.dump({"argv": sys.argv[1:], "env": {k: os.environ.get(k) for k in
               ("SWARM_ROLE", "PRODUCTSWARM_HOME", "CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_API_KEY")},
               "cwd": os.getcwd()}, f)
sys.stdout.write(%r)
sys.stderr.write("stderr: " + %r)
result = os.environ.get("FAKE_RESULT")
if result:
    print(result)
"""


def result(subtype="success", is_error=False, **extra):
    return json.dumps({"type": "result", "subtype": subtype, "is_error": is_error, "num_turns": 12,
                       "total_cost_usd": 1.25, "result": "Reviewed PR #70: request changes.\n::error::x",
                       "session_id": SID, "usage": {"input_tokens": 9}, **extra})


class Run(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.root = self.dir / "checkout"
        (self.root / "roles").mkdir(parents=True)
        (self.root / "roles" / "reviewer.md").write_text("# reviewer\n")
        self.manifest(cap="spend_cap_usd = 2.5", turns="max_turns = 7")
        bin_dir = self.dir / "bin"
        bin_dir.mkdir()
        fake = bin_dir / "claude"
        fake.write_text(FAKE % (TRANSCRIPT, TRANSCRIPT))
        fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
        (self.dir / "runner").mkdir()
        self.log = self.dir / "fake.json"
        self.env = {"PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}", "GITHUB_ACTIONS": "true",
                    "RUNNER_TEMP": str(self.dir / "runner"), "FAKE_LOG": str(self.log),
                    "CLAUDE_CODE_OAUTH_TOKEN": "oauth-secret", "FAKE_RESULT": result()}
        self.lines = []

    def manifest(self, cap="", turns=""):
        (self.root / "swarm.toml").write_text(TOML.format(cap=cap, turns=turns))

    def run_it(self, dry_run=False, **env):
        e = {**self.env, **env}
        e = {k: v for k, v in e.items() if v is not None}
        with unittest.mock.patch.object(actions_review.manifest, "ROOT", self.root):
            return actions_review.run(70, dry_run=dry_run, env=e, root=self.root,
                                      manifest_path=self.root / "swarm.toml", out=self.lines.append,
                                      clock=lambda: 1000.0, new_id=lambda: SID)

    def fake_ran(self):
        return json.loads(self.log.read_text()) if self.log.exists() else None

    # ---- the command

    def test_argv_is_headless_args_for_the_reviewer(self):
        self.assertEqual(self.run_it(), actions_review.DONE)
        argv = self.fake_ran()["argv"]
        entry = swarm.Started("reviewer-pr-70", "reviewer", "claude-test-1", SID, 1000.0, pr=70,
                              by="actions", budget_usd=2.5, max_turns=7)
        quoted = swarm.Launcher.headless_args(entry)
        self.assertEqual(argv, ["--model", "claude-test-1", "--session-id", SID,
                                "-p", swarm.opener("reviewer", None, 70),
                                *shlex.split(" ".join(quoted))])
        self.assertIn("review PR #70 only", argv[argv.index("-p") + 1])

    def test_budget_and_turns_come_from_swarm_toml(self):
        self.run_it()
        argv = self.fake_ran()["argv"]
        self.assertEqual(argv[argv.index("--max-budget-usd") + 1], "2.5")    # reviewer's spend_cap_usd
        self.assertEqual(argv[argv.index("--max-turns") + 1], "7")           # [watch] max_turns
        self.assertEqual(argv[argv.index("--permission-mode") + 1], "auto")  # GOV-0013
        self.assertEqual(argv[-2:], ["--output-format", "json"])

    def test_no_cap_or_no_max_turns_never_starts(self):
        for cap, turns in (("", "max_turns = 7"), ("spend_cap_usd = 2.5", "")):
            self.manifest(cap=cap, turns=turns)
            self.lines.clear()
            self.assertEqual(self.run_it(), actions_review.REFUSED)
            self.assertIsNone(self.fake_ran())
            self.assertIn("GOV-0012", self.lines[-1])

    def test_hooks_and_stop_hook_entry(self):
        self.run_it()
        got = self.fake_ran()
        self.assertEqual(got["env"]["SWARM_ROLE"], "reviewer")
        self.assertEqual(Path(got["cwd"]).resolve(), self.root.resolve())
        home = Path(got["env"]["PRODUCTSWARM_HOME"])
        self.assertEqual(home.parent, self.dir / "runner")                   # thrown away with the runner
        (entry,) = json.loads((home / "launcher" / "sessions.json").read_text())
        self.assertEqual((entry["session_id"], entry["by"], entry["pr"], entry["role"]),
                         (SID, "actions", 70, "reviewer"))
        settings = json.loads((self.root / ".claude" / "settings.local.json").read_text())
        commands = [h["command"] for g in settings["hooks"]["Stop"] for h in g["hooks"]]
        self.assertTrue(any(str(self.root / "heartbeat" / "hook.py") in c for c in commands))
        self.assertTrue(any(str(self.root / "launcher" / "stophook.py") in c for c in commands))
        self.assertIn("SessionStart", settings["hooks"])

    # ---- what's printed (GOV-0016)

    def test_prints_only_the_four_fields(self):
        self.run_it()
        printed = "\n".join(self.lines)
        for leak in ("assistant:", "tool_result", "ghs_leaky", "oauth-secret", "usage", "input_tokens", SID):
            self.assertNotIn(leak, printed)
        fields = [ln.split(":", 1)[0] for ln in self.lines[1:]]
        self.assertEqual(fields, list(actions_review.FIELDS))
        self.assertEqual(json.loads(self.lines[1].split(": ", 1)[1]), "Reviewed PR #70: request changes.\n::error::x")
        # one line each, and none can be read as an Actions workflow command
        self.assertEqual(len(self.lines), 5)
        self.assertFalse(any(ln.startswith("::") for ln in self.lines))

    def test_transcript_stays_in_files_on_the_runner(self):
        self.run_it()
        home = Path(self.fake_ran()["env"]["PRODUCTSWARM_HOME"])
        self.assertIn("ghs_leaky", (home / "launcher" / f"{SID}.result.json").read_text())
        self.assertIn("stderr:", (home / "launcher" / f"{SID}.stderr").read_text())

    # ---- exit codes

    def test_exit_codes(self):
        cases = [(result(), actions_review.DONE),
                 (result("error_max_turns", True), actions_review.AT_CAP),
                 (result("error_max_budget_usd", True), actions_review.AT_CAP),
                 (result("error_during_execution", True), actions_review.ERROR),
                 (result("success", True), actions_review.ERROR),
                 (None, actions_review.ERROR)]                                # no JSON result
        for res, code in cases:
            with self.subTest(res=res and json.loads(res)["subtype"]):
                self.lines.clear()
                self.assertEqual(self.run_it(FAKE_RESULT=res), code)
                if res is None:
                    self.assertEqual(self.lines[-1], "run: no JSON result from claude")

    def test_claude_missing_is_an_error(self):
        self.assertEqual(self.run_it(PATH="/nonexistent"), actions_review.ERROR)
        self.assertIn("can't start claude", self.lines[-1])

    # ---- credentials (#208)

    def test_runs_with_either_credential(self):
        for name in actions_review.CREDENTIALS:
            with self.subTest(name):
                env = {k: None for k in actions_review.CREDENTIALS}
                env[name] = "x"
                self.log.unlink(missing_ok=True)
                self.assertEqual(self.run_it(**env), actions_review.DONE)
                got = self.fake_ran()["env"]
                self.assertEqual(got[name], "x")
                other = [k for k in actions_review.CREDENTIALS if k != name][0]
                self.assertIsNone(got[other])                 # passed through as is, none added

    def test_neither_credential_fails_clearly(self):
        code = self.run_it(CLAUDE_CODE_OAUTH_TOKEN=None, ANTHROPIC_API_KEY="")
        self.assertEqual(code, actions_review.REFUSED)
        self.assertIsNone(self.fake_ran())
        self.assertEqual(len(self.lines), 1)
        for name in actions_review.CREDENTIALS:
            self.assertIn(name, self.lines[0])

    # ---- outside Actions, and --dry-run

    def test_refuses_outside_actions(self):
        self.assertEqual(self.run_it(GITHUB_ACTIONS=None), actions_review.REFUSED)
        self.assertIsNone(self.fake_ran())
        self.assertFalse((self.root / ".claude").exists())

    def test_dry_run_prints_the_command_and_starts_nothing(self):
        code = self.run_it(dry_run=True, GITHUB_ACTIONS=None, CLAUDE_CODE_OAUTH_TOKEN=None)
        self.assertEqual(code, actions_review.DONE)
        self.assertIsNone(self.fake_ran())
        self.assertFalse((self.root / ".claude").exists())
        self.assertEqual(list((self.dir / "runner").iterdir()), [])
        argv = shlex.split(self.lines[-1])
        self.assertEqual(argv[0], "claude")
        self.assertEqual(argv[argv.index("--max-turns") + 1], "7")

    def test_main_parses_run(self):
        with unittest.mock.patch.object(actions_review, "run", return_value=0) as r:
            self.assertEqual(actions_review.main(["run", "--pr", "70", "--dry-run"]), 0)
        r.assert_called_once_with(70, dry_run=True, manifest_path=None)
